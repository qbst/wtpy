"""
WonderTrader WebSocket推送服务器模块

该模块提供了基于WebSocket的实时消息推送功能，用于向Web客户端推送交易事件、
日志消息等实时数据。支持分组推送和广播推送两种模式。

主要功能：
1. WebSocket连接管理：管理客户端WebSocket连接的建立和断开
2. 消息推送：支持向所有客户端广播消息，或向特定分组推送消息
3. 分组订阅：客户端可以订阅特定的分组，只接收该分组的消息
4. 心跳机制：支持客户端心跳检测，保持连接活跃
5. 异步消息处理：使用后台线程处理消息队列，避免阻塞主线程

设计模式：
- 使用观察者模式，通过消息队列实现异步消息推送
- 使用发布-订阅模式，支持分组订阅和广播
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .WtLogger import WtLogger
import asyncio
import json
import threading
import time

class PushServer:
    """
    WebSocket推送服务器类
    
    提供基于WebSocket的实时消息推送服务，用于向Web客户端推送交易事件、
    日志消息等实时数据。支持分组推送和广播推送。
    
    使用示例：
        app = FastAPI()
        pushServer = PushServer(app, dataMgr, logger)
        pushServer.run()
        pushServer.notifyGrpLog("group1", "tag", 1234567890, "日志消息")
    """

    def __init__(self, app:FastAPI, dataMgr, logger:WtLogger = None):
        """
        初始化推送服务器
        
        创建推送服务器实例，设置FastAPI应用、数据管理器和日志记录器。
        
        @param app: FastAPI应用实例，用于注册WebSocket路由
        @param dataMgr: 数据管理器实例，用于管理数据
        @param logger: 日志记录器实例（WtLogger，默认None），用于记录日志
        """
        # 保存FastAPI应用引用
        self.app = app
        # 保存数据管理器引用
        self.dataMgr = dataMgr
        # 保存日志记录器引用
        self.logger = logger
        # 服务器就绪标志，表示服务器是否已启动
        self.ready = False

        # 活跃的WebSocket连接列表，存储所有已连接的客户端
        self.active_connections = list()

        # 广播消息锁，用于保护广播操作时的线程安全
        self.lock = threading.Lock()

        # 消息队列锁，用于保护消息队列的线程安全
        self.mutex = threading.Lock()
        # 待推送的消息队列，存储待发送的消息
        self.messages = list()
        # 后台工作线程引用，用于处理消息队列
        self.worker:threading.Thread = None
        # 停止标志，用于控制工作线程的运行
        self.stopped = False

    async def connect(self, ws: WebSocket):
        """
        处理WebSocket连接
        
        接受客户端的WebSocket连接请求，并将连接添加到活跃连接列表。
        
        @param ws: WebSocket连接对象（WebSocket），客户端连接
        """
        # 接受WebSocket连接请求，建立连接
        await ws.accept()

        # 如果WebSocket会话中包含tokeninfo（用户认证信息）
        if "tokeninfo" in ws.session:
            # 获取用户认证信息
            tInfo = ws.session["tokeninfo"]
            # 如果认证信息不为空，记录连接日志
            if tInfo is not None:
                self.logger.info(f"{tInfo['loginid']} connected")
            # 将WebSocket连接对象添加到活跃连接列表
            self.active_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        """
        处理WebSocket断开连接
        
        从活跃连接列表中移除断开的连接，并记录日志。
        
        @param ws: WebSocket连接对象（WebSocket），要断开的连接
        """
        # 从活跃连接列表中移除WebSocket连接对象
        self.active_connections.remove(ws)
        # 如果WebSocket会话中包含tokeninfo（用户认证信息）
        if "tokeninfo" in ws.session:
            # 获取用户认证信息
            tInfo = ws.session["tokeninfo"]
            # 如果认证信息不为空，记录断开连接日志
            if tInfo is not None:
                self.logger.info(f"{tInfo['loginid']} disconnected")

    @staticmethod
    async def send_personal_message(data: dict, ws: WebSocket):
        """
        发送个人消息（静态方法）
        
        向指定的WebSocket连接发送JSON格式的消息。
        
        @param data: 要发送的数据字典
        @param ws: WebSocket连接对象（WebSocket），目标连接
        """
        # 通过WebSocket发送JSON格式的消息
        await ws.send_json(data)

    def broadcast(self, data: dict, groupid:str=""):
        """
        广播消息
        
        向所有活跃的WebSocket连接广播消息。如果指定了groupid，则只向订阅了该分组的连接发送。
        
        @param data: 要广播的数据字典
        @param groupid: 分组ID（字符串，默认空字符串），如果为空则广播给所有连接，否则只发送给订阅了该分组的连接
        """
        # 获取广播锁，确保广播操作的线程安全
        self.lock.acquire()

        # 尝试获取当前事件循环
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except:
            # 如果获取失败，设置为None
            loop = None
        
        # 如果事件循环为空或已关闭，创建新的事件循环
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 创建任务列表，用于存储所有发送任务
        tasks = []
        # 遍历所有活跃的WebSocket连接
        for ws in self.active_connections:
            # 如果指定了分组ID，且连接未订阅该分组，则跳过
            if len(groupid)!=0 and "groupid" in ws.session and ws.session["groupid"]!=groupid:
                continue
            # 创建发送任务，添加到任务列表
            tasks.append(asyncio.ensure_future(ws.send_json(data)))
        
        # 如果有任务，等待所有任务完成
        if len(tasks) > 0:            
            loop.run_until_complete(asyncio.gather(*tasks))

        # 关闭事件循环
        loop.close()
        # 释放广播锁
        self.lock.release()

    def on_subscribe_group(self, ws:WebSocket, data:dict):
        """
        处理分组订阅请求
        
        当客户端请求订阅某个分组时，将此分组ID保存到WebSocket会话中。
        
        @param ws: WebSocket连接对象（WebSocket），请求订阅的客户端连接
        @param data: 订阅请求数据字典，应包含"groupid"字段
        """
        # 如果WebSocket连接不在活跃连接列表中，直接返回
        if ws not in self.active_connections:
            return

        # 如果请求数据中不包含groupid字段，直接返回
        if "groupid" not in data:
            return

        # 获取用户认证信息
        tokenInfo = ws.session["tokeninfo"]
        # 将分组ID保存到WebSocket会话中
        ws.session["groupid"] = data["groupid"]
        # 记录分组订阅日志
        self.logger.info("{}@{} subscribed group {}".format(tokenInfo["loginid"], tokenInfo["loginip"] , data["groupid"]))

    def run(self):
        """
        启动推送服务器
        
        注册WebSocket路由，启动后台消息处理线程。
        此函数会注册"/"路径的WebSocket端点，并启动消息处理循环。
        """
        # 获取FastAPI应用实例
        app = self.app
        # 注册WebSocket路由，路径为"/"
        @app.websocket("/")
        async def ws_listen(ws:WebSocket):
            """
            WebSocket监听处理函数
            
            处理WebSocket连接的生命周期，包括连接建立、消息接收和断开连接。
            """
            # 接受WebSocket连接
            await self.connect(ws)
            try:
                # 持续接收消息，直到连接断开
                while True:
                    # 接收文本消息
                    data = await ws.receive_text()
                    try:
                        # 将JSON格式的消息解析为字典
                        req = json.loads(data)
                        # 获取消息类型
                        tp = req["type"]
                        # 如果是订阅请求
                        if tp == 'subscribe':
                            # 处理分组订阅
                            self.on_subscribe_group(ws,req)
                            # 发送确认消息
                            await self.send_personal_message(req, ws)
                        # 如果是心跳消息
                        elif tp == 'heartbeat':
                            # 发送心跳响应
                            await self.send_personal_message({"type":"heartbeat", "message":"pong"}, ws)
                    except:
                        # 如果消息解析失败，继续处理下一条消息
                        continue

            except WebSocketDisconnect:
                # 如果WebSocket连接断开，处理断开连接
                self.disconnect(ws)
        # 设置服务器就绪标志为True
        self.ready = True

        # 创建后台工作线程，用于处理消息队列
        self.worker = threading.Thread(target=self.loop, daemon=True)
        # 启动工作线程
        self.worker.start()

    def loop(self):
        """
        消息处理循环
        
        后台线程函数，持续从消息队列中取出消息并广播。
        此函数会一直运行，直到stopped标志为True。
        """
        # 持续运行，直到停止标志为True
        while not self.stopped:
            # 如果消息队列为空，等待1秒后继续
            if len(self.messages) == 0:
                time.sleep(1)
                continue
            
            # 获取消息队列锁
            self.mutex.acquire()
            # 复制消息列表，避免长时间持有锁
            messages = self.messages.copy()
            # 清空消息队列
            self.messages = []
            # 释放消息队列锁
            self.mutex.release()

            # 遍历所有待发送的消息
            for msg in messages:
                # 如果是分组日志消息，向指定分组广播
                if msg["type"] == "gplog":
                    self.broadcast(msg, msg["groupid"])
                else:
                    # 否则向所有连接广播
                    self.broadcast(msg)

    def notifyGrpLog(self, groupid, tag:str, time:int, message):
        """
        通知分组日志消息
        
        向指定分组推送日志消息。消息会被添加到消息队列，由后台线程处理。
        
        @param groupid: 分组ID（字符串），目标分组
        @param tag: 日志标签（字符串），用于标识日志来源
        @param time: 日志时间（整数），时间戳格式
        @param message: 日志消息内容（任意类型），要推送的日志消息
        """
        # 如果服务器未就绪，直接返回
        if not self.ready:
            return

        # 获取消息队列锁
        self.mutex.acquire()
        # 将日志消息添加到消息队列
        self.messages.append({"type":"gplog", "groupid":groupid, "tag":tag, "time":time, "message":message})
        # 释放消息队列锁
        self.mutex.release()

    def notifyGrpEvt(self, groupid, evttype):
        """
        通知分组事件
        
        向指定分组推送事件通知。消息会被添加到消息队列，由后台线程处理。
        
        @param groupid: 分组ID（字符串），目标分组
        @param evttype: 事件类型（字符串），事件类型标识
        """
        # 如果服务器未就绪，直接返回
        if not self.ready:
            return

        # 获取消息队列锁
        self.mutex.acquire()
        # 将事件消息添加到消息队列
        self.messages.append({"type":"gpevt", "groupid":groupid, "evttype":evttype})
        # 释放消息队列锁
        self.mutex.release()

    def notifyGrpChnlEvt(self, groupid, chnlid, evttype, data):
        """
        通知分组通道事件
        
        向指定分组推送交易通道事件。消息会被添加到消息队列，由后台线程处理。
        
        @param groupid: 分组ID（字符串），目标分组
        @param chnlid: 通道ID（字符串），交易通道标识
        @param evttype: 事件类型（字符串），事件类型标识
        @param data: 事件数据（任意类型），事件相关的数据
        """
        # 如果服务器未就绪，直接返回
        if not self.ready:
            return

        # 获取消息队列锁
        self.mutex.acquire()
        # 将通道事件消息添加到消息队列
        self.messages.append({"type":"chnlevt", "groupid":groupid, "channel":chnlid, "data":data, "evttype":evttype})
        # 释放消息队列锁
        self.mutex.release()
