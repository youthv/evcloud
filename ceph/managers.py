import os

import rados, rbd  #yum install python36-rbd.x86_64 python-rados.x86_64

from .models import CephCluster


class RadosError(rados.Error):
    '''def __init__(self, message, errno=None)'''
    pass


class ImageExistsError(RadosError):
    '''def __init__(self, message, errno=None)'''
    pass


def get_rbd_manager(ceph:CephCluster, pool_name:str):
    '''
    获取一个rbd管理接口对象

    :param ceph: ceph配置模型对象CephCluster()
    :param pool_name: pool名称
    :return:
        RbdManager()    # success
        raise RadosError   # failed

    :raise RadosError
    '''
    conf_file = ceph.config_file
    keyring_file = ceph.keyring_file
    # 当水平部署多个服务时，在后台添加ceph配置时，只有其中一个服务保存了配置文件，要检查当前服务是否保存到配置文件了
    if not os.path.exists(conf_file) or not os.path.exists(keyring_file):
        ceph.save()
        conf_file = ceph.config_file
        keyring_file = ceph.keyring_file

    return RbdManager(conf_file=conf_file, keyring_file=keyring_file, pool_name=pool_name)


class RbdManager:
    '''
    ceph rbd 操作管理接口
    '''
    def __init__(self, conf_file:str, keyring_file:str, pool_name:str):
        '''
        raise RadosError
        '''
        if not os.path.exists(conf_file):
            raise RadosError("参数有误，配置文件路径不存在")
        self._conf_file = conf_file

        if keyring_file and not os.path.exists(keyring_file):
            raise RadosError("参数有误，keyring配置文件路径不存在")
        self._keyring_file = keyring_file

        self.pool_name = pool_name
        self._cluster = None
        self._cluster = self.get_cluster()    # 与ceph连接的Rados对象

    def __enter__(self):
        self.get_cluster()
        return self

    def __exit__(self, type_, value, traceback):
        self.shutdown()
        return False  # __exit__返回的是False，有异常不被忽略会向上抛出。

    def __del__(self):
        self.shutdown()

    def shutdown(self):
        '''关闭与ceph的连接'''
        if self._cluster:
            self._cluster.shutdown()
            self._cluster = None

    def get_cluster(self):
        '''
        获取已连接到ceph集群的Rados对象
        :return:
            success: Rados()
        :raises: class:`RadosError`
        '''
        if self._cluster and self._cluster.state == 'connected':
            return self._cluster

        try:
            self._cluster = rados.Rados(conffile=self._conf_file, conf={'keyring': self._keyring_file})
            self._cluster.connect(timeout=5)
            return self._cluster
        except rados.Error as e:
            msg = e.args[0] if e.args else 'error connecting to the cluster'
            raise RadosError(msg)

    def create_snap(self, image_name: str, snap_name: str, protected: bool = False):
        '''
        为一个rbd image(卷)创建快照

        :param image_name: 要创建快照的rbd卷名称
        :param snap_name: 快照名称
        :param protected: 是否设置快照protect; 默认False(不protect)
        :return:
            True    # success
            raise RadosError # failed

        :raise class: `RadosError`
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                with rbd.Image(ioctx=ioctx, name=image_name) as image:
                    image.create_snap(snap_name)  # Create a snapshot of the image.
                    if protected:
                        image.protect_snap(snap_name)
        except Exception as e:
            raise RadosError(f'create_snap error:{str(e)}')

        return True

    def rename_image(self, image_name:str, new_name:str):
        '''
        重命名一个rbd image

        :param image_name: 被重命名的image卷名称
        :param new_name: image的新名称
        :return:
            True    # success
            raise RadosError # failed

        :raise class: `RadosError`
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                rbd.RBD().rename(ioctx=ioctx, src=image_name, dest=new_name)
        except rbd.ImageNotFound as e:
            raise RadosError('rename_image error: image not found')
        except Exception as e:
            raise RadosError(f'rename_image error:{str(e)}')

        return True

    def remove_image(self, image_name:str):
        '''
        删除一个rbd image，删除前需要删除所有的快照

        :param image_name: image name
        :return:
            True    # success
            raise RadosError # failed

        :raise class: `RadosError`
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                rbd.RBD().remove(ioctx=ioctx, name=image_name)
        except rbd.ImageNotFound as e:
            return True
        except Exception as e:
            raise RadosError(f'remove_image error:{str(e)}')

        return True

    def clone_image(self, snap_image_name:str, snap_name:str, new_image_name:str, data_pool=None):
        '''
        从快照克隆一个rbd image

        :param snap_image_name: 快照父image名称
        :param snap_name: 快照名称
        :param new_image_name: 新克隆的image名称
        :param data_pool: 如果指定，数据存储的到此pool
        :return:
            True    # success
            raise RadosError # failed

        :raise class: `RadosError`, ImageExistsError
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as p_ioctx:
                c_ioctx = p_ioctx   # 克隆的image元数据保存在同一个pool，通过data_pool参数可指定数据块存储到data_pool
                rbd.RBD().clone(p_ioctx=p_ioctx, p_name=snap_image_name, p_snapname=snap_name, c_ioctx=c_ioctx,
                                c_name=new_image_name, data_pool=data_pool)
        except rbd.ImageExists as e:
            raise ImageExistsError(f'clone_image error,image exists,{str(e)}')
        except Exception as e:
            raise RadosError(f'clone_image error:{str(e)}')

        return True

    def list_images(self):
        '''
        获取pool中所有image

        :return:
            list    # success
            raise RadosError # failed

        :raise class: `RadosError`
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                return  rbd.RBD().list(ioctx)  # 返回 Image name list
        except Exception as e:
            raise RadosError(f'rename_image error:{str(e)}')

    def create_image(self, name:str, size:int, data_pool=None):
        '''
        Create an rbd image.

        :param name: what the image is called
        :param size: how big the image is in bytes
        :param data_pool: 如果指定，数据存储的到此pool
        :return:
            True    # success
            None    # image already exists

        :raises: FunctionNotSupported, RadosError
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                rbd.RBD().create(ioctx=ioctx, name=name, size=size, old_format=False, data_pool=data_pool)
        except rbd.ImageExists as e:
            return None
        except (TypeError, rbd.InvalidArgument, Exception) as e:
            raise RadosError(f'create_image error:{str(e)}')

        return True

    def list_image_snaps(self, name:str):
        '''
        获取rbd image的所有快照
        :param name: rbd image
        :return:
            list    # success
        :raises: RadosError
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                with rbd.Image(ioctx=ioctx, name=name) as image:
                    return list(image.list_snaps())
        except Exception as e:
            raise RadosError(f'list_image_snaps error:{str(e)}')

    def remove_snap(self, image_name:str, snap:str):
        '''
        删除一个rbd image快照
        :param snap: 快照名称
        :param image_name: rbd image名称
        :return:
            True    # success
        :raises: RadosError
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                with rbd.Image(ioctx=ioctx, name=image_name) as image:
                    if image.is_protected_snap(snap):   # protected snap check
                        image.unprotect_snap(snap)
                    image.remove_snap(snap)
        except rbd.ObjectNotFound as e:
            return True
        except Exception as e:
            raise RadosError(f'remove_snap error:{str(e)}')
        return True

    def image_rollback_to_snap(self, image_name:str, snap:str):
        '''
        rbd image回滚到历史快照

        :param snap: 快照名称
        :param image_name: rbd image名称
        :return:
            True    # success
        :raises: RadosError
        '''
        cluster = self.get_cluster()
        try:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                with rbd.Image(ioctx=ioctx, name=image_name) as image:
                    image.rollback_to_snap(snap)
        except Exception as e:
            raise RadosError(f'rollback_to_snap error:{str(e)}')
        return True

    def get_rbd_image(self, image_name:str):
        '''
        获取rbd image对象, 使用close_rbd_image()关闭

        :param image_name: rbd image名称
        :return:
            rbd.Image()
        :raises: RadosError
        '''
        cluster = self.get_cluster()
        try:
            ioctx = cluster.open_ioctx(self.pool_name)
            image = rbd.Image(ioctx=ioctx, name=image_name)
            return image
        except Exception as e:
            raise RadosError(f'rollback_to_snap error:{str(e)}')

    def close_rbd_image(self, image):
        try:
            image.close()
            image.ioctx.close()
        except Exception:
            pass


class CephClusterManager:
    '''
    CEPH集群管理器
    '''

    def get_ceph_by_id(self, ceph_id: int):
        '''
        通过id获取ceph集群配置对象

        :param ceph_id: ceph集群id
        :return:
            Host() # success
            None    #不存在
        :raise RadosError
        '''
        if not isinstance(ceph_id, int) or ceph_id <= 0:
            raise RadosError('CEPH集群ID参数有误')

        try:
            return CephCluster.objects.filter(id=ceph_id).first()
        except Exception as e:
            raise RadosError(f'查询CEPH集群时错误,{str(e)}')




