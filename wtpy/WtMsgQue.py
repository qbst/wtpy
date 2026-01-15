"""
消息队列模块

本模块提供了消息队列（MQ）功能的Python封装，用于实现不同组件之间的消息通信。
消息队列支持发布-订阅模式，允许消息服务器发布消息，多个客户端订阅并接收消息。
这对于分布式系统、多策略通信等场景非常有用。

主要功能：
1. WtMQServer：消息队列服务器，负责发布消息到指定主题
2. WtMQClient：消息队列客户端，负责订阅主题并接收消息
3. WtMsgQue：消息队列管理器，单例模式，统一管理所有服务器和客户端
"""

# 导入消息队列的底层包装器和回调函数类型
from wtpy.wrapper.WtMQWrapper import WtMQWrapper, CB_ON_MSG
# 导入单例装饰器
from wtpy.WtUtilDefs import singleton

class WtMQServer:
    """
    消息队列服务器类
    
    负责创建和管理消息队列服务器，可以向指定主题发布消息。
    多个客户端可以订阅这些主题并接收消息。
    """

    def __init__(self):
        """
        构造函数
        
        初始化消息队列服务器，此时尚未绑定到底层实现，需要调用init方法进行初始化。
        """
        # 服务器ID，由底层分配，初始化时为None
        self.id = None

    def init(self, wrapper:WtMQWrapper, id:int):
        """
        初始化消息队列服务器
        
        将服务器绑定到底层的消息队列实现，并分配服务器ID。
        
        @wrapper: 底层消息队列包装器对象
        @id: 底层分配的服务器ID
        """
        # 保存服务器ID
        self.id = id
        # 保存底层包装器引用，用于调用底层接口
        self.wrapper = wrapper

    def publish_message(self, topic:str, message:str):
        """
        发布消息到指定主题
        
        将消息发布到指定的主题，所有订阅了该主题的客户端都会收到这条消息。
        
        @topic: 主题名称，字符串类型
        @message: 要发布的消息内容，字符串类型
        @raise Exception: 如果服务器未初始化则抛出异常
        """
        # 检查服务器是否已初始化
        if self.id is None:
            raise Exception("MQServer not initialzied")

        # 调用底层接口发布消息
        self.wrapper.publish_message(self.id, topic, message)

class WtMQClient:
    """
    消息队列客户端类
    
    负责创建和管理消息队列客户端，可以订阅指定主题并接收消息。
    当订阅的主题有新消息时，会触发on_mq_message回调函数。
    """

    def __init__(self):
        """
        构造函数
        
        初始化消息队列客户端，此时尚未绑定到底层实现，需要调用init方法进行初始化。
        """
        return

    def init(self, wrapper:WtMQWrapper, id:int):
        """
        初始化消息队列客户端
        
        将客户端绑定到底层的消息队列实现，并分配客户端ID。
        
        @wrapper: 底层消息队列包装器对象
        @id: 底层分配的客户端ID
        """
        # 保存客户端ID
        self.id = id
        # 保存底层包装器引用，用于调用底层接口
        self.wrapper = wrapper

    def start(self):
        """
        启动客户端
        
        启动消息队列客户端，开始接收订阅主题的消息。
        调用此方法后，客户端才能正常接收消息。
        
        @raise Exception: 如果客户端未初始化则抛出异常
        """
        # 检查客户端是否已初始化
        if self.id is None:
            raise Exception("MQClient not initialzied")

        # 调用底层接口启动客户端
        self.wrapper.start_client(self.id)

    def subscribe(self, topic:str):
        """
        订阅指定主题
        
        订阅一个主题后，该主题的所有消息都会通过on_mq_message回调函数传递给客户端。
        
        @topic: 要订阅的主题名称，字符串类型
        @raise Exception: 如果客户端未初始化则抛出异常
        """
        # 检查客户端是否已初始化
        if self.id is None:
            raise Exception("MQClient not initialzied")
        # 调用底层接口订阅主题
        self.wrapper.subcribe_topic(self.id, topic)

    def on_mq_message(self, topic:str, message:str, dataLen:int):
        """
        消息接收回调函数
        
        当订阅的主题有新消息时，底层会调用此函数。
        子类可以重写此函数来实现自定义的消息处理逻辑。
        
        @topic: 消息所属的主题名称
        @message: 消息内容
        @dataLen: 消息数据长度
        """
        pass

@singleton
class WtMsgQue:
    """
    消息队列管理器类（单例模式）
    
    统一管理所有的消息队列服务器和客户端，提供创建、销毁等操作。
    采用单例模式确保整个应用中只有一个管理器实例。
    """

    def __init__(self) -> None:
        """
        构造函数
        
        初始化消息队列管理器，创建底层包装器并设置消息回调。
        由于使用了单例装饰器，此构造函数只会被调用一次。
        """
        # 存储所有服务器的字典，键为服务器ID，值为WtMQServer对象
        self._servers = dict()
        # 存储所有客户端的字典，键为客户端ID，值为WtMQClient对象
        self._clients = dict()
        # 创建底层消息队列包装器，传入self作为回调对象
        self._wrapper = WtMQWrapper(self)

        # 创建消息回调函数，当底层收到消息时会调用self.on_mq_message
        self._cb_msg = CB_ON_MSG(self.on_mq_message)

    def get_client(self, client_id:int) -> WtMQClient:
        """
        根据客户端ID获取客户端对象
        
        @client_id: 客户端ID
        @return: 返回对应的WtMQClient对象，如果不存在则返回None
        """
        # 检查客户端ID是否存在
        if client_id not in self._clients:
            return None
        
        # 返回对应的客户端对象
        return self._clients[client_id]

    def on_mq_message(self, client_id:int, topic:str, message:str, dataLen:int):
        """
        消息接收回调函数（由底层调用）
        
        当底层收到消息时，会调用此函数。此函数会找到对应的客户端对象，
        并调用客户端的on_mq_message方法。
        
        @client_id: 接收消息的客户端ID
        @topic: 消息所属的主题名称
        @message: 消息内容
        @dataLen: 消息数据长度
        """
        # 根据客户端ID获取客户端对象
        client = self.get_client(client_id)
        # 如果客户端不存在，直接返回
        if client is None:
            return

        # 调用客户端的消息处理函数
        client.on_mq_message(topic, message, dataLen)

    def add_mq_server(self, url:str, server:WtMQServer = None) -> WtMQServer:
        """
        添加消息队列服务器
        
        创建一个新的消息队列服务器并注册到管理器中。
        
        @url: 服务器连接URL，用于连接到消息队列服务
        @server: 可选的服务器对象，如果为None则创建新对象
        @return: 返回服务器对象
        """
        # 调用底层接口创建服务器，返回服务器ID
        id = self._wrapper.create_server(url)
        # 如果未提供服务器对象，则创建新对象
        if server is None:
            server = WtMQServer()

        # 初始化服务器对象
        server.init(self._wrapper, id)
        # 将服务器注册到管理器中
        self._servers[id] = server
        # 返回服务器对象
        return server

    def destroy_mq_server(self, server:WtMQServer):
        """
        销毁消息队列服务器
        
        从管理器中移除服务器并销毁底层资源。
        
        @server: 要销毁的服务器对象
        """
        # 获取服务器ID
        id = server.id
        # 检查服务器是否存在于管理器中
        if id not in self._servers:
            return
        
        # 调用底层接口销毁服务器
        self._wrapper.destroy_server(id)
        # 从管理器中移除服务器
        self._servers.pop(id)

    def add_mq_client(self, url:str, client:WtMQClient = None) -> WtMQClient:
        """
        添加消息队列客户端
        
        创建一个新的消息队列客户端并注册到管理器中。
        
        @url: 客户端连接URL，用于连接到消息队列服务
        @client: 可选的客户端对象，如果为None则创建新对象
        @return: 返回客户端对象
        """
        # 调用底层接口创建客户端，传入消息回调函数，返回客户端ID
        id = self._wrapper.create_client(url, self._cb_msg)
        # 如果未提供客户端对象，则创建新对象
        if client is None:
            client = WtMQClient()
        # 初始化客户端对象
        client.init(self._wrapper, id)
        # 将客户端注册到管理器中
        self._clients[id] = client
        # 返回客户端对象
        return client

    def destroy_mq_client(self, client:WtMQClient):
        """
        销毁消息队列客户端
        
        从管理器中移除客户端并销毁底层资源。
        
        @client: 要销毁的客户端对象
        """
        # 获取客户端ID
        id = client.id
        # 检查客户端是否存在于管理器中
        if id not in self._clients:
            return
        
        # 调用底层接口销毁客户端
        self._wrapper.destroy_client(id)
        # 从管理器中移除客户端
        self._clients.pop(id)
        
