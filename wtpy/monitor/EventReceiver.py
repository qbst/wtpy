"""
WonderTrader事件接收器模块

该模块提供了基于消息队列的事件接收功能，用于接收实盘交易和回测过程中的各种事件。
通过消息队列（WtMsgQue）实现进程间通信，支持订阅不同类型的事件主题。

主要功能：
1. 实盘交易事件接收：接收订单、成交、通知、日志等事件
2. 回测事件接收：接收回测启动、结束、状态、资金变化等事件
3. 自动编码检测：使用chardet自动检测消息编码，确保正确解码
4. 事件回调机制：通过Sink接口将事件传递给上层处理

设计模式：
- 使用观察者模式，通过EventSink和BtEventSink接口实现事件回调
- 使用消息队列模式，实现异步事件传递
"""

import json
import chardet

from wtpy import WtMsgQue, WtMQClient

# ========== 全局消息队列实例 ==========
# 创建全局消息队列实例，用于管理所有消息队列客户端
mq = WtMsgQue()

# ========== 实盘交易事件主题常量 ==========
# 生产环境下的成交通知主题，当有成交发生时，会向此主题推送消息
TOPIC_RT_TRADE = "TRD_TRADE"
# 生产环境下的订单通知主题，当订单状态变化时，会向此主题推送消息
TOPIC_RT_ORDER = "TRD_ORDER"
# 生产环境下的普通通知主题，用于推送一般的通知消息
TOPIC_RT_NOTIFY = "TRD_NOTIFY"
# 生产环境下的日志通知主题，用于推送日志消息
TOPIC_RT_LOG = "LOG"
# 消息超时通知主题，当消息接收超时时，会向此主题推送消息
TOPIC_TIMEOUT = "TIMEOUT"

class EventSink:
    """
    实盘交易事件回调接口类
    
    定义了实盘交易过程中各种事件的回调接口。
    用户需要继承此类并实现相应的方法来处理事件。
    
    使用示例：
        class MyEventSink(EventSink):
            def on_order(self, chnl, ordInfo):
                print(f"收到订单: {ordInfo}")
    """
    
    def __init__(self):
        """
        初始化事件回调接口
        
        基类构造函数，子类可以重写此方法进行初始化。
        """
        pass

    def on_order(self, chnl:str, ordInfo:dict):
        """
        订单事件回调函数
        
        当收到订单状态变化事件时，会调用此函数。
        
        @param chnl: 交易通道名称（字符串），标识订单来源的交易接口
        @param ordInfo: 订单信息字典，包含订单的详细信息（订单号、状态、价格、数量等）
        """
        pass

    def on_trade(self, chnl:str, trdInfo:dict):
        """
        成交事件回调函数
        
        当收到成交事件时，会调用此函数。
        
        @param chnl: 交易通道名称（字符串），标识成交来源的交易接口
        @param trdInfo: 成交信息字典，包含成交的详细信息（成交价、成交量、成交时间等）
        """
        pass
    
    def on_notify(self, chnl:str, message:str):
        """
        通知事件回调函数
        
        当收到普通通知事件时，会调用此函数。
        
        @param chnl: 交易通道名称（字符串），标识通知来源的交易接口
        @param message: 通知消息内容（字符串）
        """
        pass

    def on_log(self, tag:str, time:int, message:str):
        """
        日志事件回调函数
        
        当收到日志事件时，会调用此函数。
        
        @param tag: 日志标签（字符串），用于标识日志来源
        @param time: 日志时间（整数），时间戳格式
        @param message: 日志消息内容（字符串）
        """
        pass

    def on_timeout(self):
        """
        超时事件回调函数
        
        当消息接收超时时，会调用此函数。
        用于检测消息队列连接是否正常。
        """
        pass

def decode_bytes(data:bytes):
    """
    字节数据解码函数
    
    使用chardet自动检测字节数据的编码格式，然后解码为字符串。
    如果检测失败，则使用默认编码（UTF-8）进行解码。
    
    @param data: 需要解码的字节数据（bytes）
    @return: 解码后的字符串
    """
    # 使用chardet检测字节数据的编码格式
    ret = chardet.detect(data)
    # 如果检测结果不为空
    if ret is not None:
        # 获取检测到的编码格式
        encoding = ret["encoding"]
        # 如果编码格式不为空，使用检测到的编码进行解码
        if encoding is not None:
            return data.decode(encoding)
        else:
            # 如果编码格式为空，使用默认编码（UTF-8）进行解码
            return data.decode()
    else:
        # 如果检测结果为空，使用默认编码（UTF-8）进行解码
        return data.decode()

class EventReceiver(WtMQClient):
    """
    实盘交易事件接收器类
    
    继承自WtMQClient，用于接收实盘交易过程中的各种事件。
    通过消息队列订阅不同主题的事件，并将事件传递给EventSink处理。
    
    使用示例：
        sink = MyEventSink()
        receiver = EventReceiver("ipc:///wtpy/trade.ipc", 
                                 topics=[TOPIC_RT_TRADE, TOPIC_RT_ORDER],
                                 sink=sink)
        receiver.run()
    """

    def __init__(self, url:str, topics:list = [], sink:EventSink = None, logger = None):
        """
        初始化事件接收器
        
        创建事件接收器实例，连接到指定的消息队列URL，并订阅指定的事件主题。
        
        @param url: 消息队列URL（字符串），如"ipc:///wtpy/trade.ipc"或"tcp://127.0.0.1:9000"
        @param topics: 要订阅的事件主题列表（列表，默认空列表），如[TOPIC_RT_TRADE, TOPIC_RT_ORDER]
        @param sink: 事件回调接口实例（EventSink，默认None），用于处理接收到的事件
        @param logger: 日志记录器（默认None），用于记录日志
        """
        # 保存消息队列URL
        self.url = url
        # 保存日志记录器引用
        self.logger = logger
        # 将当前实例添加到消息队列管理器，建立连接
        mq.add_mq_client(url, self)
        # 遍历订阅列表，订阅所有指定的事件主题
        for topic in topics:
            self.subscribe(topic)

        # 停止标志，用于控制接收器的运行状态
        self._stopped = False
        # 工作线程引用，用于后台接收消息
        self._worker = None
        # 事件回调接口实例
        self._sink = sink

    def on_mq_message(self, topic:str, message:str, dataLen:int):
        """
        消息队列消息接收回调函数
        
        当消息队列收到消息时，会调用此函数。
        根据消息主题类型，解析消息内容并调用相应的回调函数。
        
        @param topic: 消息主题（字节字符串），需要解码
        @param message: 消息内容（字节字符串），需要解码
        @param dataLen: 消息数据长度（整数），用于截取有效数据
        """
        # 将主题从字节字符串解码为Python字符串
        topic = decode_bytes(topic)
        # 如果消息数据长度大于0，截取有效数据并解码
        if dataLen > 0:
            message = decode_bytes(message[:dataLen])
        else:
            # 如果消息数据长度为0，设置为None
            message = None
            
        # 如果事件回调接口存在，根据主题类型处理消息
        if self._sink is not None:
            # 如果是成交通知主题
            if topic == TOPIC_RT_TRADE:
                # 将JSON格式的消息解析为字典对象
                msgObj = json.loads(message)
                # 提取交易通道名称
                trader = msgObj["trader"]
                # 从消息对象中移除trader字段，剩余字段作为成交信息
                msgObj.pop("trader")
                # 调用成交事件回调函数
                self._sink.on_trade(trader, msgObj)
            # 如果是订单通知主题
            elif topic == TOPIC_RT_ORDER:
                # 将JSON格式的消息解析为字典对象
                msgObj = json.loads(message)
                # 提取交易通道名称
                trader = msgObj["trader"]
                # 从消息对象中移除trader字段，剩余字段作为订单信息
                msgObj.pop("trader")
                # 调用订单事件回调函数
                self._sink.on_order(trader, msgObj)
            # 如果是普通通知主题
            elif topic == TOPIC_RT_NOTIFY:
                # 将JSON格式的消息解析为字典对象
                msgObj = json.loads(message)
                # 提取交易通道名称
                trader = msgObj["trader"]
                # 调用通知事件回调函数，传递交易通道和消息内容
                self._sink.on_notify(trader, msgObj["message"])
            # 如果是日志通知主题
            elif topic == TOPIC_RT_LOG:
                # 将JSON格式的消息解析为字典对象
                msgObj = json.loads(message)
                # 调用日志事件回调函数，传递日志标签、时间和消息内容
                self._sink.on_log(msgObj["tag"], msgObj["time"], msgObj["message"])
            # 如果是超时通知主题
            elif topic == TOPIC_TIMEOUT:
                # 调用超时事件回调函数
                self._sink.on_timeout()

    def run(self):
        """
        启动事件接收器
        
        开始接收消息队列中的消息。此函数会启动后台线程持续接收消息。
        """
        # 调用父类的start方法，启动消息接收
        self.start()

    def release(self):
        """
        释放事件接收器资源
        
        停止接收消息并释放相关资源。在程序退出前应调用此函数。
        """
        # 从消息队列管理器中移除当前客户端，断开连接
        mq.destroy_mq_client(self)

# ========== 回测事件主题常量 ==========
# 回测环境下的事件主题，主要通知回测的启动和结束
TOPIC_BT_EVENT  = "BT_EVENT"
# 回测的状态主题，用于推送回测过程中的状态信息
TOPIC_BT_STATE  = "BT_STATE"
# 每日资金变化主题，用于推送回测过程中每日的资金变化情况
TOPIC_BT_FUND   = "BT_FUND"

class BtEventSink:
    """
    回测事件回调接口类
    
    定义了回测过程中各种事件的回调接口。
    用户需要继承此类并实现相应的方法来处理回测事件。
    
    使用示例：
        class MyBtEventSink(BtEventSink):
            def on_begin(self):
                print("回测开始")
    """
    
    def __init__(self):
        """
        初始化回测事件回调接口
        
        基类构造函数，子类可以重写此方法进行初始化。
        """
        pass
    
    def on_begin(self):
        """
        回测开始事件回调函数
        
        当回测开始时，会调用此函数。
        """
        pass
    
    def on_finish(self):
        """
        回测结束事件回调函数
        
        当回测结束时，会调用此函数。
        """
        pass

    def on_fund(self, fundInfo:dict):
        """
        资金变化事件回调函数
        
        当回测过程中资金发生变化时，会调用此函数。
        
        @param fundInfo: 资金信息字典，包含资金变化的详细信息（日期、权益、盈亏等）
        """
        pass

    def on_state(self, statInfo:float):
        """
        回测状态事件回调函数
        
        当回测状态更新时，会调用此函数。
        
        @param statInfo: 状态信息（字典），包含回测的当前状态信息（进度、当前日期等）
        """
        pass

class BtEventReceiver(WtMQClient):
    """
    回测事件接收器类
    
    继承自WtMQClient，用于接收回测过程中的各种事件。
    通过消息队列订阅回测相关的事件主题，并将事件传递给BtEventSink处理。
    
    使用示例：
        sink = MyBtEventSink()
        receiver = BtEventReceiver("ipc:///wtpy/bt_test.ipc",
                                   topics=[TOPIC_BT_EVENT, TOPIC_BT_STATE],
                                   sink=sink)
        receiver.run()
    """

    def __init__(self, url:str, topics:list = [], sink:BtEventSink = None, logger = None):
        """
        初始化回测事件接收器
        
        创建回测事件接收器实例，连接到指定的消息队列URL，并订阅指定的事件主题。
        
        @param url: 消息队列URL（字符串），如"ipc:///wtpy/bt_test.ipc"
        @param topics: 要订阅的事件主题列表（列表，默认空列表），如[TOPIC_BT_EVENT, TOPIC_BT_STATE]
        @param sink: 回测事件回调接口实例（BtEventSink，默认None），用于处理接收到的事件
        @param logger: 日志记录器（默认None），用于记录日志
        """
        # 保存消息队列URL
        self.url = url
        # 保存日志记录器引用
        self.logger = logger
        # 将当前实例添加到消息队列管理器，建立连接
        mq.add_mq_client(url, self)
        # 遍历订阅列表，订阅所有指定的事件主题
        for topic in topics:
            self.subscribe(topic)

        # 停止标志，用于控制接收器的运行状态
        self._stopped = False
        # 工作线程引用，用于后台接收消息
        self._worker = None
        # 回测事件回调接口实例
        self._sink = sink

    def on_mq_message(self, topic:str, message:str, dataLen:int):
        """
        消息队列消息接收回调函数
        
        当消息队列收到消息时，会调用此函数。
        根据消息主题类型，解析消息内容并调用相应的回调函数。
        
        @param topic: 消息主题（字节字符串），需要解码
        @param message: 消息内容（字节字符串），需要解码
        @param dataLen: 消息数据长度（整数），用于截取有效数据
        """
        # 将主题从字节字符串解码为Python字符串
        topic = decode_bytes(topic)
        # 将消息内容从字节字符串解码为Python字符串
        message = decode_bytes(message[:dataLen])
        # 如果回测事件回调接口存在，根据主题类型处理消息
        if self._sink is not None:
            # 如果是回测事件主题
            if topic == TOPIC_BT_EVENT:
                # 如果消息内容是"BT_START"，表示回测开始
                if message == 'BT_START':
                    # 调用回测开始回调函数
                    self._sink.on_begin()
                else:
                    # 否则表示回测结束，调用回测结束回调函数
                    self._sink.on_finish()
            # 如果是回测状态主题
            elif topic == TOPIC_BT_STATE:
                # 将JSON格式的消息解析为字典对象
                msgObj = json.loads(message)
                # 调用回测状态回调函数，传递状态信息
                self._sink.on_state(msgObj)
            # 如果是资金变化主题
            elif topic == TOPIC_BT_FUND:
                # 将JSON格式的消息解析为字典对象
                msgObj = json.loads(message)
                # 调用资金变化回调函数，传递资金信息
                self._sink.on_fund(msgObj)

    def run(self):
        """
        启动回测事件接收器
        
        开始接收消息队列中的消息。此函数会启动后台线程持续接收消息。
        """
        # 调用父类的start方法，启动消息接收
        self.start()

    def release(self):
        """
        释放回测事件接收器资源
        
        停止接收消息并释放相关资源。在程序退出前应调用此函数。
        """
        # 从消息队列管理器中移除当前客户端，断开连接
        mq.destroy_mq_client(self)
