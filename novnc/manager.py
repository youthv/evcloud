#coding=utf-8
#@author:   hai #@email:   zhhaim@qq.cn #@date:     2019-10-16
#@desc:    novnc token管理模块。完成读写novnc的token配置文件到数据库			

import uuid
import subprocess

from django.conf import settings
from django.utils import timezone

from .models import Token
from utils.errors import NovncError


class NovncTokenManager(object):
    def generate_token(self, vmid:str, hostip:str):
        '''
        创建虚拟机vnc url

        :param vmid:
        :param hostip:
        :return:
            (vnc_id:str, vnc_url:str)   # success

        :raise: NovncError
        '''
        vncport = self.get_vm_vncinfo(vmid, hostip)
        now = timezone.now()
        #删除该hostip和vncport的历史token记录
        Token.objects.filter(ip = hostip).filter(port = vncport).filter(expiretime__lt=now).delete()
        #创建新的token记录
        novnc_token = str(uuid.uuid4())
        new_token = Token.objects.create(token = novnc_token, ip = hostip, port = vncport, expiretime = now)
 
        #删除（一年前 到 3天前）之间有更新的，现在过期的所有token记录
        start_time = now - timezone.timedelta(days=365)   #print(start_time);
        end_time   = now - timezone.timedelta(days=3)     #print(end_time);
        Token.objects.filter(updatetime__range=(start_time, end_time)).filter(expiretime__lt=now).delete()   #注意 __range表示范围
        return(novnc_token, f"/novnc/?vncid={novnc_token}")

    def del_token(self, vncid):
        Token.objects.filter(token = str(vncid)).delete()

    def get_vm_vncinfo(self, vmid, hostip):
        '''
        获取虚拟机的vnc端口

        :param vmid:
        :param hostip:
        :return:
            port: str   # success
        :raise: NovncError
        '''
        cmd = f'ssh {hostip} virsh vncdisplay {vmid}'
        (res, info) = subprocess.getstatusoutput(cmd)
        if res != 0:
            raise NovncError(msg=info)

        port = False
        for line in info.split('\n'):
            line = line.strip()
            if len(line) > 0 and line[0] == ':':
                if line[1:].isdigit():
                    port = settings.VNCSERVER_BASE_PORT + int(line[1:])
                    break
        if port == False:
            raise NovncError(msg='get vnc port error')

        return str(port)

