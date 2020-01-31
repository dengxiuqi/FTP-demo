import socketserver, pickle
import configparser
import os, sys
import hashlib
import time
from conf import settings

STATUS_CODE = {
    250 : "Invalid cmd format, e.g:{'action':'get','filename':'generator.py','size':344}",
    251 : "Invalid cmd",
    252 : "Invalid auth Data",
    253 : "Wrong username or password",
    254 : "Passed authenticate",
    255 : "Filename isn't provided by client",
    256 : "Filename isn't existing",
    257 : "Ready to send file",
    258 : "MD5 Verification",
    259 : "Send list to client",
    260 : "Invalid path",
    261 : "Don't have permission",
    262 : "Open new dirpath",
    263 : "The dir is existing",
    264 : "The dirname is wrong",
    265 : "Dir has been created"
}

class FTPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            self.data = self.request.recv(1024).strip()     #一直接收客户端消息
            print("{} wrote:".format(self.client_address[0]))
            if not self.data:   #如果收到的是空数据，则表明客户端断开了连接
                print("client closed...")
                break
            data = pickle.loads(self.data)
            print(data)
            if data.get("action") is not None:
                if hasattr(self, "_%s"%data.get("action")):
                    func = getattr(self, "_%s"%data.get("action"))
                    func(data)
                else:   #指令错误
                    print("invalid cmd")
                    self.send_response(251)
            else:   #缺乏指令
                print("invalid cmd format")
                self.send_response(250)

    def _auth(self, *args, **kwargs):
        '''用户登录验证'''
        data = args[0]
        if data.get("username") is None or data.get("password") is None:    #数据不全
            print(STATUS_CODE.get(252))
            self.response(252)
        user = self.authenticate(data.get("username"), data.get("password"))
        self.user = user["Username"]
        if user is None:    #用户名或密码错误
            print(STATUS_CODE.get(253))
            self.send_response(253)
        else:   #通过验证
            print(STATUS_CODE.get(254), user)
            self.send_response(254)
            self.user_home_dir = os.path.abspath("%s/%s" % (settings.USER_HOME, self.user))  #登录成功就对用户家目录
            self.user_added_dir = ""  #对附加路径赋值为空

    def authenticate(self, username, password):
        '''验证用户合法性，合法就返回用户数据'''
        config = configparser.ConfigParser()
        config.read(settings.ACCOUNT_FILE)
        if username in config.sections():
            _password = config[username]["Password"]
            config[username]['Username'] = username     #返回用户名，供后面调用
            if _password == password:
                print("pass auth..", username)
                return config[username]

    def _put(self, *args, **kwargs):
        pass

    def _get(self, *args, **kwargs):
        '''下载文件'''
        data = args[0]
        if data.get('action') is None:
            self.send_response(255)
        file_abs_path = "%s/%s/%s"%(self.user_home_dir, self.user_added_dir, data.get('filename'))    #文件路径=用户家目录+附加路径+文件名

        if os.path.isfile(file_abs_path):
            if self.user_home_dir not in os.path.abspath(file_abs_path):  # 绝对路径中必须包含家目录，否则没有权限
                self.send_response(261)
                return False
            file_obj = open(file_abs_path, "rb")
            file_size = os.path.getsize(file_abs_path)
            self.send_response(257, data = {'file_size': file_size})
            self.request.recv(1024)    #防止粘包，等待客户端确认
            if data.get('md5'):
                md5_obj = hashlib.md5()
                for line in file_obj:
                    self.request.send(line)
                    md5_obj.update(line)
                else:
                    self.request.recv(1024)  # 防止粘包，等待客户端确认
                    file_obj.close()
                    print("---Send done---")
                    print("md5 is:", md5_obj.hexdigest())
                    self.send_response(258, data = {'md5': md5_obj.hexdigest()})
            else:
                for line in file_obj:
                    self.request.send(line)
                else:
                    file_obj.close()
                    print("---Send done---")
        else:
            self.send_response(256)



    def _ls(self, *args, **kwargs):
        '''显示文件列表'''
        current_dir = "%s/%s" % (self.user_home_dir, self.user_added_dir)
        ls_path = args[0]["path"]
        ls_cmd = args[0]["cmd"]
        if not os.path.isdir("%s/%s"%(current_dir, ls_path)):   #检测路径是否有效
            self.send_response(260)
            return False
        if self.user_home_dir not in os.path.abspath("%s/%s"%(current_dir, ls_path)):    #绝对路径中必须包含家目录，否则没有权限
            self.send_response(261)
            return False
        user_file_list = os.listdir("%s/%s"%(current_dir, ls_path))   #获取文件和目录名
        list_data = {"dir":[], "file":[]}    #初始化要发送给用户的数据
        for obj in user_file_list:
            if os.path.isdir(os.path.abspath("%s/%s/%s" % (current_dir, ls_path, obj))):   #如果是目录
                list_data["dir"].append("%s     ……dir"%obj)   #目录的格式比较特殊，方便用户区分
                if ls_cmd == "-l":  # 如果附加参数是-l
                    list_data["dir"][-1] +="   %s   %s"%(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(os.path.abspath("%s/%s/%s" % (current_dir, ls_path, obj))))), os.path.getsize(os.path.abspath("%s/%s/%s" % (current_dir, ls_path, obj))))
            else:                             #否则就是文件
                list_data["file"].append(obj)
                if ls_cmd == "-l":  # 如果附加参数是-l
                    list_data["file"][-1] +="   %s   %s"%(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(os.path.abspath("%s/%s/%s" % (current_dir, ls_path, obj))))), os.path.getsize(os.path.abspath("%s/%s/%s" % (current_dir, ls_path, obj))))

        self.send_response(259, data=list_data)      #发送数据


    def _cd(self, *args, **kwargs):
        '''打开新的路径'''
        current_dir = "%s/%s" % (self.user_home_dir, self.user_added_dir)
        cd_path = args[0]['path']
        if not os.path.isdir("%s/%s" % (current_dir, cd_path)):  # 检测路径是否有效
            self.send_response(260)
            return False
        elif self.user_home_dir not in os.path.abspath("%s/%s" % (current_dir, cd_path)):  # 绝对路径中必须包含家目录，否则没有权限
            self.send_response(261)
            return False
        self.user_added_dir = os.path.abspath("%s/%s" % (current_dir, cd_path)).replace(self.user_home_dir, '')   #更新附加路径
        self.send_response(262)



    def _mkdir(self, *args, **kwargs):
        current_dir = "%s/%s" % (self.user_home_dir, self.user_added_dir)
        dirname_list = args[0]['dirname']
        for dirname in dirname_list:
            dir_path, dir_name = os.path.split(dirname)
            if not os.path.isdir("%s/%s" % (current_dir, dir_path)):  # 检测路径是否有效
                self.send_response(260)
            elif self.user_home_dir not in os.path.abspath("%s/%s" % (current_dir, dir_path)):  # 绝对路径中必须包含家目录，否则没有权限
                self.send_response(261)
            elif dir_name in os.listdir("%s/%s" % (current_dir, dir_path)): #如果文件名已存在
                self.send_response(263)
            else:
                try:
                    os.mkdir(os.path.abspath("%s/%s/%s" % (current_dir, dir_path, dir_name)))   #创建
                    self.send_response(265)
                except OSError:
                    self.send_response(264)
            self.request.recv(1024)      #防止粘包


    def send_response(self, status_code, data = None):  #data是个数组
        '''向客户端返回数据'''
        response = {'status_code':status_code, 'status_msg': STATUS_CODE[status_code]}
        if type(status_code) is int:    #如果是报错，那么在服务器端也显示
            print(STATUS_CODE.get(status_code))
        if data:
            response.update(data)
        self.request.send(pickle.dumps(response))


if __name__ == "__main__":
    HOST, PORT = "localhost", 8000

    # Create the server, binding to localhost on port 9999
    server = socketserver.ThreadingTCPServer((HOST, PORT), FTPHandler)

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    server.serve_forever()