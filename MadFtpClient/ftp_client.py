import socket, optparse, pickle
import hashlib
import os, sys

class FTPClient(object):
    def __init__(self):
        self.parser = optparse.OptionParser()
        self.parser.add_option("-s", "--server", dest="server", help="ftp server ip_addr")
        self.parser.add_option("-P", "--port", dest="port", type="int", help="ftp sever port")
        self.parser.add_option("-u", "--username", dest="username", help="username")
        self.parser.add_option("-p", "--password", dest="password", help="password")
        self.options, self.args = self.parser.parse_args()
        self.verify_args(self.options, self.args)
        self.make_connection()

    def make_connection(self):
        '''建立连接'''
        self.client = socket.socket()
        self.client.connect((self.options.server, self.options.port))

    def verify_args(self, options, args):
        '''校验并调用相应的功能'''
        #用户名和密码，要么两个都有，要么两个都没有
        if not (options.username or options.password):
            pass
        elif options.username is None or options.password is None:
            exit(print("Err: username and password must be provided together"))
        elif getattr(options, "server") and getattr(options, "port"):
            if options.port > 0 and options.port < 65535:
                return True
            else:
                print("Err:host port must be in 0-65535")
        else:
            self.parser.print_help()

    def authenticate(self):
        '''用户验证'''
        if self.options.username:
            return self.get_auth_result(self.options.username, self.options.password)
        else:
            retry_count = 0
            while retry_count < 3:
                self.options.username = input("username:").strip()
                self.options.password = input("password:").strip()
                if self.get_auth_result(self.options.username, self.options.password) is True:
                    # self.user = self.options.username #定义一个当前用户，为Interaction里人机交互使用
                    return True
                retry_count += 1


    def get_auth_result(self, username, password):
        '''得到验证结果'''
        data = {"action":"auth",
                "username":username,
                "password":password}
        self.client.send(pickle.dumps(data))
        res = self.get_response()
        if res.get('status_code') is 254:
            print("Passed authentication!")
            return True
        else:
            print(res.get("status_msg"))
            return False

    def get_response(self):
        '''得到服务器回复结果'''
        data = self.client.recv(1024)
        data = pickle.loads(data)
        return data

    def interactive(self):
        '''验证完毕，进入用户交互界面'''
        if self.authenticate():
            print("--start interactive with u---")
            while True:
                choice = input("[%s]"%self.options.username).strip()
                if choice == "exit" or choice == "exit()" :
                    print("Exit the client progress")
                    break
                if len(choice) == 0 : continue
                cmd_list = choice.split()
                if hasattr(self, "_%s"%cmd_list[0]):
                    func = getattr(self, "_%s"%cmd_list[0])
                    func(cmd_list)
                else:
                    print("Invalid cmd")

    def __md5_required(self, cmd_list):
        '''检测命令是否需要MD5验证'''
        if "--md5" in cmd_list:
            return True

    def progress_bar(self, total_size):
        '''
        进度条
        迭代器
        '''
        now_size = 0
        current_size = 0
        bar_num =0
        while now_size<total_size:
            if int(now_size/total_size*100) > current_size + 5:
                print("#", end="", flush=True)
                bar_num += 1
                current_size = int(now_size/total_size*100/5) * 5
            now_size = yield
        if bar_num < 20:    #确保打印20个“#”，美观
            for i in range(20-bar_num):
                print("#", end="", flush=True)

    def _get(self, cmd_list):
        '''
        从服务器上下载文件
        '''
        print("get--", cmd_list)
        if len(cmd_list) == 1:
            print("No filename follows")
            return
        data = {
            'action' : 'get',
            'filename' : cmd_list[1]
        }
        if self.__md5_required(cmd_list):
            data['md5'] = True
        self.client.send(pickle.dumps(data))
        res = self.get_response()
        self.client.send(b'1')
        print(res)
        if res.get('status_code') == 257:
            recv_percentage = self.progress_bar(res['file_size'])   #进度条
            recv_percentage.__next__()      #用__next__()__启动迭代器，否则会报错
            base_file_name = cmd_list[1].split('/')[-1]
            file_obj = open(base_file_name, "wb")
            received_size = 0
            if self.__md5_required(cmd_list):       #需要md5验证
                md5_obj = hashlib.md5()
                while received_size < res['file_size']:
                    data = self.client.recv(1024)
                    received_size += len(data)
                    file_obj.write(data)
                    md5_obj.update(data)
                    try:
                        recv_percentage.send(received_size)
                    except StopIteration as e:      #抓取迭代完成时的错误
                        print("100%")
                else:
                    print("--->file received done---")
                    file_obj.close()
                    self.client.send(b'1')
                    data = self.get_response()
                    if data['status_code'] == 258:
                        if md5_obj.hexdigest() == data['md5']:
                            print("---The file is right---")
                        else:
                            print("---Somewhere of file is wrong---")
            else:                               #不需要md5验证
                while received_size < res['file_size']:
                    data = self.client.recv(1024)
                    received_size += len(data)
                    file_obj.write(data)
                    try:
                        recv_percentage.send(received_size)
                    except StopIteration as e:
                        print("100%")
                else:
                    print("--->file received done---")
                    file_obj.close()

    def _ls(self, cmd_list):
        '''
        打印当前目录的文件列表
        目前最多仅支持一个操作符
        '''
        print("ls--", cmd_list)
        if len(cmd_list) == 1:
            data = {'action': 'ls', 'path': '', 'cmd': '' } #操作符和路径都为空
        elif len(cmd_list) == 2:
            if '-' in cmd_list[1]:     #ls后跟的是操作符
                data = {'action': 'ls', 'path': '', 'cmd':  cmd_list[1]}
            else:                       #ls后跟的是路径
                data = {'action': 'ls', 'path': cmd_list[1], 'cmd': ''}
        elif len(cmd_list) == 3:
            if '-' in cmd_list[1]:     #ls后跟的是操作符
                data = {'action': 'ls', 'path': cmd_list[2], 'cmd':  cmd_list[1]}
            else:                       #ls后跟的是路径
                data = {'action': 'ls', 'path': cmd_list[1], 'cmd': cmd_list[2]}
        self.client.send(pickle.dumps(data))
        res = self.get_response()
        if res["status_code"]==259:         #如果收到的是目录信息
            # print("---the list as follows---")
            for obj in res["dir"]:
                print(obj)       #打印文件目录
            for obj in res["file"]:
                print(obj)
        elif res["status_code"]==260:
            print("Invalid path")
        elif res["status_code"]==261:
            print("Don't have permission")

    def _cd(self, cmd_list):
        '''
        打开新的路径
        '''
        print("cd--", cmd_list)
        if len(cmd_list) == 1:
            print("Must have pathname, example: cd dirname")
            return
        elif len(cmd_list) > 2:
            print("Wrong format, example: cd dirname")
        if len(cmd_list) == 2:
            data = {'action': 'cd', 'path': cmd_list[1]}
        self.client.send(pickle.dumps(data))
        res = self.get_response()
        if res["status_code"]==262:     #成功打开新路径
            # print("Open new dirpath")
            return
        elif res["status_code"] == 260:
            print("Invalid path")
        elif res["status_code"] == 261:
            print("Don't have permission")

    def _mkdir(self, cmd_list):
        '''
        创建文件夹
        '''
        print("mkdir--", cmd_list)
        if len(cmd_list) == 1:
            print("Must have pathname, example: mkdir dirname1 dirname2")
            return
        else:
            data = {'action': 'mkdir', 'dirname': []}
            for dirname in cmd_list[1:]:  #将要创建的文件名生成为列表
                data['dirname'].append(dirname)
        self.client.send(pickle.dumps(data))
        for dirname in  data['dirname']:
            res = self.get_response()
            if res["status_code"] == 265:
                print(dirname,":Dir has been created")
            elif res["status_code"] == 260:
                print(dirname,":Invalid path")
            elif res["status_code"] == 261:
                print(dirname,":Don't have permission")
            elif res["status_code"] == 263:
                print(dirname,":The dir is existing")
            elif res["status_code"] == 264:
                print(dirname,":The dirname is wrong")
            self.client.send(b'1')




if __name__ == "__main__":
    ftp = FTPClient()
    ftp.interactive()