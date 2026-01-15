"""
消息队列包装器模块

本模块提供WonderTrader消息队列组件的Python接口封装，用于实现进程间或组件间的消息通信。
支持发布-订阅模式的消息传递，可以创建消息服务器和客户端，实现数据的实时推送和订阅。

主要功能：
1. 创建和管理消息服务器
2. 创建和管理消息客户端
3. 发布消息到指定主题
4. 订阅指定主题的消息
5. 日志回调处理

使用单例模式确保全局只有一个消息队列包装器实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import cdll, CFUNCTYPE, c_uint32, c_bool, c_void_p, c_char_p, c_ulong
# 导入平台辅助工具，用于获取动态库路径
from .PlatformHelper import PlatformHelper as ph
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入操作系统模块
import os

# 定义消息回调函数类型：消息ID、主题、消息内容、消息长度
CB_ON_MSG = CFUNCTYPE(c_void_p,  c_uint32, c_char_p, c_char_p, c_uint32)
# 定义日志回调函数类型：日志ID、日志消息、是否为服务器日志
CB_ON_LOG = CFUNCTYPE(c_void_p,  c_uint32, c_char_p, c_bool)

# Python对接C接口的库
@singleton
class WtMQWrapper:
    """
    WonderTrader消息队列组件C接口底层对接模块
    
    提供消息队列功能的Python封装，支持创建服务器和客户端，实现消息的发布和订阅。
    使用单例模式，确保全局只有一个实例。
    """

    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"
    
    # 构造函数，传入消息管理器
    def __init__(self, mgr):
        """
        初始化消息队列包装器
        
        @param mgr: 消息管理器对象
        """
        # 保存消息管理器引用
        self._mgr = mgr
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取消息队列动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtMsgQue")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)

        # 创建日志回调函数
        self._cb_log = CB_ON_LOG(self.on_mq_log)
        # 注册日志回调函数到C++库
        self.api.regiter_callbacks(self._cb_log)

        # 设置create_server函数的参数类型：服务器URL（字符串）
        self.api.create_server.argtypes = [c_char_p]
        # 设置create_server函数的返回类型：服务器ID（无符号长整型）
        self.api.create_server.restype = c_ulong

    def on_mq_log(self, id:int, message:str, bServer:bool):
        """
        消息队列日志回调函数
        
        当C++库产生日志时，会调用此函数。
        
        @param id: 日志ID
        @param message: 日志消息（字节串）
        @param bServer: 是否为服务器日志
        """
        # 将字节串解码为字符串并打印
        print(message.decode())

    def create_server(self, url:str):
        """
        创建消息服务器
        
        @param url: 服务器URL地址
        @return int: 服务器ID，用于后续操作
        """
        # 调用C++库创建服务器，返回服务器ID
        return self.api.create_server(bytes(url, 'utf-8'))

    def destroy_server(self, id:int):
        """
        销毁消息服务器
        
        @param id: 服务器ID
        """
        # 调用C++库销毁指定ID的服务器
        self.api.destroy_server(id)

    def publish_message(self, id:int, topic:str, message:str):
        """
        发布消息到指定主题
        
        @param id: 服务器ID
        @param topic: 主题名称
        @param message: 消息内容
        """
        # 将消息内容转换为UTF-8字节串
        message = bytes(message, 'utf-8')
        # 调用C++库发布消息：服务器ID、主题、消息内容、消息长度
        self.api.publish_message(id, bytes(topic, 'utf-8'), message, len(message))

    def create_client(self, url:str, cbMsg:CB_ON_MSG):
        """
        创建消息客户端
        
        @param url: 服务器URL地址
        @param cbMsg: 消息回调函数，当收到消息时调用
        @return int: 客户端ID，用于后续操作
        """
        # 调用C++库创建客户端，返回客户端ID
        return self.api.create_client(bytes(url, 'utf-8'), cbMsg)

    def destroy_client(self, id:int):
        """
        销毁消息客户端
        
        @param id: 客户端ID
        """
        # 调用C++库销毁指定ID的客户端
        self.api.destroy_client(id)

    def subcribe_topic(self, id:int, topic:str):
        """
        订阅指定主题的消息
        
        @param id: 客户端ID
        @param topic: 要订阅的主题名称
        """
        # 调用C++库订阅主题
        self.api.subscribe_topic(id, bytes(topic, 'utf-8'))

    def start_client(self, id:int):
        """
        启动消息客户端
        
        客户端启动后开始接收订阅主题的消息。
        
        @param id: 客户端ID
        """
        # 调用C++库启动指定ID的客户端
        self.api.start_client(id)

