"""
WonderTrader监控服务器模块

该模块提供了基于FastAPI的Web监控服务器，用于管理和监控WonderTrader交易系统。
主要功能包括：
1. 用户认证和权限管理：支持用户登录、权限验证、会话管理
2. 组合管理：提供组合的增删改查、配置管理、状态查询等功能
3. 策略管理：查询策略列表、策略数据（交易、资金、持仓等）
4. 交易通道管理：查询交易通道的订单、成交、持仓、资金等信息
5. 看门狗服务：管理应用的启动、停止、重启和监控
6. 回测管理：集成回测管理器，提供回测任务的创建和管理
7. 实时数据推送：通过WebSocket向客户端推送实时交易事件和日志
8. 日志查询：查询系统日志和应用日志

设计模式：
- 使用FastAPI构建RESTful API接口
- 使用SessionMiddleware管理用户会话
- 使用WebSocket实现实时数据推送
- 使用AES加密保护用户认证信息
- 使用看门狗服务监控应用生命周期

主要作用：
- 为WonderTrader交易系统提供一个Web管理界面
- 方便用户通过浏览器管理和监控交易系统
- 提供统一的API接口供第三方系统集成
"""

from fastapi import FastAPI, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, FileResponse
import uvicorn

import json
import yaml
import datetime
import os
import hashlib
import sys
import chardet
import pytz
import base64

from .WtLogger import WtLogger
from .DataMgr import DataMgr, backup_file
from .PushSvr import PushServer
from .WatchDog import WatchDog, WatcherSink
from .WtBtMon import WtBtMon
from wtpy import WtDtServo
import signal
import platform

def isWindows():
    """
    判断当前操作系统是否为Windows
    
    @return: 如果是Windows系统返回True，否则返回False
    """
    if "windows" in platform.system().lower():
        return True

    return False

def get_session(request: Request, key: str):
    """
    从会话中获取指定键的值
    
    @param request: FastAPI请求对象，包含会话信息
    @param key: 会话键名（字符串），要获取的键
    @return: 会话值，如果键不存在则返回None
    """
    if key not in request["session"]:
        return None
    return request["session"][key]

def set_session(request: Request, key: str, val):
    """
    设置会话中指定键的值
    
    @param request: FastAPI请求对象，包含会话信息
    @param key: 会话键名（字符串），要设置的键
    @param val: 会话值，要设置的值
    """
    request["session"][key] = val

def pop_session(request: Request, key: str):
    """
    从会话中删除指定键
    
    @param request: FastAPI请求对象，包含会话信息
    @param key: 会话键名（字符串），要删除的键
    """
    if key not in request["session"]:
        return
    request["session"].pop(key)

def AES_Encrypt(key:str, data:str):
    """
    AES加密函数
    
    使用AES-CBC模式对数据进行加密，并使用Base64编码。
    用于加密用户认证信息等敏感数据。
    
    @param key: 加密密钥（字符串），16字节密钥
    @param data: 要加密的数据（字符串）
    @return: 加密后的Base64编码字符串
    """
    from Crypto.Cipher import AES # pip install pycryptodome
    # 初始化向量（IV），固定值
    vi = '0102030405060708'
    # 定义补位函数，确保数据长度是16的倍数
    pad = lambda s: s + (16 - len(s) % 16) * chr(16 - len(s) % 16)
    # 对数据进行补位
    data = pad(data)
    # 创建AES加密器，使用CBC模式
    cipher = AES.new(key.encode('utf8'), AES.MODE_CBC, vi.encode('utf8'))
    # 加密数据，得到bytes类型的数据
    encryptedbytes = cipher.encrypt(data.encode('utf8'))
    # 使用Base64进行编码，返回byte字符串
    encodestrs = base64.b64encode(encryptedbytes)
    # 对byte字符串按utf-8进行解码，返回字符串
    enctext = encodestrs.decode('utf8')
    return enctext

def AES_Decrypt(key:str, data:str):
    """
    AES解密函数
    
    使用AES-CBC模式对Base64编码的加密数据进行解密。
    用于解密用户认证信息等敏感数据。
    
    @param key: 解密密钥（字符串），16字节密钥，必须与加密时使用的密钥相同
    @param data: 要解密的Base64编码字符串
    @return: 解密后的原始字符串
    """
    from Crypto.Cipher import AES # pip install pycryptodome
    # 初始化向量（IV），固定值，必须与加密时使用的IV相同
    vi = '0102030405060708'
    # 将Base64编码的字符串转换为bytes类型
    data = data.encode('utf8')
    # 使用Base64解码，将加密数据转换为bytes类型数据
    encodebytes = base64.decodebytes(data)
    # 创建AES解密器，使用CBC模式
    cipher = AES.new(key.encode('utf8'), AES.MODE_CBC, vi.encode('utf8'))
    # 解密数据
    text_decrypted = cipher.decrypt(encodebytes)
    # 定义去补位函数，移除加密时添加的补位字符
    unpad = lambda s: s[0:-s[-1]]
    # 去除补位
    text_decrypted = unpad(text_decrypted)
    # 将bytes类型转换为字符串
    text_decrypted = text_decrypted.decode('utf8')
    return text_decrypted


def get_tail(filename, N: int = 100, encoding="GBK"):
    """
    获取文件最后N行的函数
    
    高效读取大文件的最后N行，避免将整个文件加载到内存。
    使用分块读取的方式，提高性能。
    
    @param filename: 文件路径（字符串），要读取的文件
    @param N: 要读取的行数（整数，默认100），返回文件的最后N行
    @param encoding: 文件编码（字符串，默认"GBK"），用于读取文件
    @return: 元组(最后N行的内容字符串, 行数)，如果文件为空则返回空字符串和0
    """
    # 获取文件大小
    filesize = os.path.getsize(filename)
    # 块大小（字节），每次读取10KB
    blocksize = 10240
    # 打开文件（使用指定编码）
    dat_file = open(filename, 'r', encoding=encoding)
    last_line = ""
    # 如果文件大小大于块大小，从倒数第二个块开始读取
    if filesize > blocksize:
        maxseekpoint = (filesize // blocksize)
        dat_file.seek((maxseekpoint - 1) * blocksize)
    elif filesize:
        # 如果文件大小小于块大小，从文件开头读取
        dat_file.seek(0, 0)
    # 读取所有行
    lines = dat_file.readlines()
    if lines:
        # 获取最后N行
        last_line = lines[-N:]
    dat_file.close()
    # 返回最后N行的内容和行数
    return ''.join(last_line), len(last_line)


def check_auth(request: Request, token:str = None, seckey:str = None):
    """
    检查用户认证状态
    
    验证用户是否已登录且会话未过期。支持两种认证方式：
    1. 从会话（session）中获取token信息
    2. 从请求参数中获取加密的token并解密
    
    @param request: FastAPI请求对象，包含会话信息
    @param token: 加密的token字符串（字符串，默认None），如果提供则使用此token，否则从session获取
    @param seckey: 解密密钥（字符串，默认None），用于解密token
    @return: 元组(是否认证成功, token信息或错误信息字典)
            - 如果认证成功：返回(True, token信息字典)
            - 如果认证失败：返回(False, 错误信息字典，包含result和message字段)
    """
    # 如果token为None，从session中获取token信息
    if token is None:
        tokeninfo = get_session(request, "tokeninfo")
        # session里没有用户信息，返回未登录错误
        if tokeninfo is None:
            return False, {
                "result": -999,
                "message": "请先登录"
            }

        # session里有用户信息，检查是否过期
        exptime = tokeninfo["expiretime"]  # 过期时间
        # 获取当前UTC时间并格式化为字符串
        now = datetime.datetime.now().replace(tzinfo=pytz.timezone('UTC')).strftime("%Y.%m.%d %H:%M:%S")
        # 如果当前时间大于过期时间，返回超时错误
        if now > exptime:
            return False, {
                "result": -999,
                "message": "登录已超时，请重新登录"
            }

        return True, tokeninfo
    else:
        # 如果提供了token，使用AES解密token
        tokeninfo = AES_Decrypt(seckey, token)
        # 如果解密失败或token为空，返回未登录错误
        if tokeninfo is None:
            return False, {
                "result": -999,
                "message": "请先登录"
            }

        # 检查token是否过期
        exptime = tokeninfo["expiretime"]  # 过期时间
        # 获取当前UTC时间并格式化为字符串
        now = datetime.datetime.now().replace(tzinfo=pytz.timezone('UTC')).strftime("%Y.%m.%d %H:%M:%S")
        # 如果当前时间大于过期时间，返回超时错误
        if now > exptime:
            return False, {
                "result": -999,
                "message": "登录已超时，请重新登录"
            }

        return True, tokeninfo

def get_cfg_tree(root: str, name: str):
    """
    获取配置文件树结构
    
    根据组合路径构建配置文件树结构，用于前端展示。
    配置文件树包括run.py、config.json/config.yaml以及配置文件中引用的其他文件。
    
    @param root: 组合根路径（字符串），组合的目录路径
    @param name: 节点名称（字符串），树节点的显示名称
    @return: 配置文件树字典，包含label（标签）、path（路径）、exist（是否存在）、isfile（是否为文件）、children（子节点列表）等字段
    """
    # 如果路径不存在，返回不存在的目录节点
    if not os.path.exists(root):
        return {
            "label": name,
            "path": root,
            "exist": False,
            "isfile": False,
            "children": []
        }

    # 如果路径是文件，返回文件节点
    if os.path.isfile(root):
        return {
            "label": name,
            "path": root,
            "exist": False,
            "isfile": True
        }

    # 创建目录节点
    ret = {
        "label": name,
        "path": root,
        "exist": True,
        "isfile": False,
        "children": []
    }

    # 添加run.py文件节点
    filepath = os.path.join(root, "run.py")
    ret['children'].append({
        "label": "run.py",
        "path": filepath,
        "exist": True,
        "isfile": True,
        "children": []
    })

    # 先尝试查找config.json文件
    filepath = os.path.join(root, "config.json")
    isYaml = False
    # 如果config.json不存在，尝试查找config.yaml文件
    if not os.path.exists(filepath):
        filepath = os.path.join(root, "config.yaml")
        isYaml = True

    # 添加配置文件节点
    ret['children'].append({
        "label": "config.yaml" if isYaml else "config.json",
        "path": filepath,
        "exist": True,
        "isfile": True,
        "children": []
    })

    # 读取配置文件内容
    f = open(filepath, "rb")
    content = f.read()
    f.close()

    # 使用chardet检测文件编码（检测前500字节）
    encoding = chardet.detect(content[:500])["encoding"]
    # 使用检测到的编码解码文件内容
    content = content.decode(encoding)

    # 根据文件类型解析配置
    if isYaml:
        # 如果是YAML文件，使用yaml.full_load解析
        cfgObj = yaml.full_load(content)
    else:
        # 如果是JSON文件，使用json.loads解析
        cfgObj = json.loads(content)

    # 如果配置中包含executers字段，添加执行器配置文件节点
    if "executers" in cfgObj:
        filename = cfgObj["executers"]
        # 如果executers是字符串类型（文件名），添加文件节点
        if type(filename) == str:
            filepath = os.path.join(root, filename)
            ret['children'].append({
                "label": filename,
                "path": filepath,
                "exist": True,
                "isfile": True,
                "children": []
            })

    # 如果配置中包含parsers字段，添加解析器配置文件节点
    if "parsers" in cfgObj:
        filename = cfgObj["parsers"]
        # 如果parsers是字符串类型（文件名），添加文件节点
        if type(filename) == str:
            filepath = os.path.join(root, filename)
            ret['children'].append({
                "label": filename,
                "path": filepath,
                "exist": True,
                "isfile": True,
                "children": []
            })

    # 如果配置中包含traders字段，添加交易接口配置文件节点
    if "traders" in cfgObj:
        filename = cfgObj["traders"]
        # 如果traders是字符串类型（文件名），添加文件节点
        if type(filename) == str:
            filepath = os.path.join(root, filename)
            ret['children'].append({
                "label": filename,
                "path": filepath,
                "exist": True,
                "isfile": True,
                "children": []
            })

    # 添加generated目录节点（递归获取子目录树）
    filepath = os.path.join(root, 'generated')
    ret["children"].append(get_path_tree(filepath, 'generated', True))

    return ret


def get_path_tree(root: str, name: str, hasFile: bool = True):
    """
    获取路径树结构
    
    递归构建指定路径的目录树结构，用于前端展示文件系统。
    目录在前，文件在后，便于前端展示。
    
    @param root: 根路径（字符串），要构建树结构的目录路径
    @param name: 节点名称（字符串），树节点的显示名称
    @param hasFile: 是否包含文件（布尔值，默认True），True表示包含文件，False表示只包含目录
    @return: 路径树字典，包含label（标签）、path（路径）、exist（是否存在）、isfile（是否为文件）、children（子节点列表）等字段
    """
    # 如果路径不存在，返回不存在的目录节点
    if not os.path.exists(root):
        return {
            "label": name,
            "path": root,
            "exist": False,
            "isfile": False,
            "children": []
        }

    # 如果路径是文件，返回文件节点
    if os.path.isfile(root):
        return {
            "label": name,
            "path": root,
            "exist": False,
            "isfile": True
        }

    # 创建目录节点
    ret = {
        "label": name,
        "path": root,
        "exist": True,
        "isfile": False,
        "children": []
    }
    # 列出目录下的所有文件和子目录
    files = os.listdir(root, )
    # 遍历所有文件和子目录
    for filename in files:
        # 跳过缓存目录和Python缓存文件
        if filename in ['__pycache__', '.vscode', 'wtpy', '__init__.py']:
            continue
        # 跳过.pyc文件（Python编译后的字节码文件）
        if filename[-3:] == 'pyc':
            continue

        # 构建完整路径
        filepath = os.path.join(root, filename)
        # 如果是文件
        if os.path.isfile(filepath):
            # 如果hasFile为False，跳过文件
            if not hasFile:
                continue
            else:
                # 添加文件节点
                ret["children"].append({
                    "label": filename,
                    "path": filepath,
                    "exist": True,
                    "isfile": True})
        else:
            # 如果是目录，递归获取子目录树
            ret["children"].append(get_path_tree(filepath, filename, hasFile))

        # 将子节点排序：目录在前，文件在后
        ay1 = list()  # 目录列表
        ay2 = list()  # 文件列表
        for item in ret["children"]:
            if item["isfile"]:
                ay2.append(item)
            else:
                ay1.append(item)
        # 合并列表：目录在前，文件在后
        ay = ay1 + ay2
        ret["children"] = ay
    return ret


class WtMonSink:
    """
    监控服务器事件回调接口类
    
    定义了监控服务器在运行过程中各种事件的回调接口。
    用户需要继承此类并实现相应的方法来处理接收到的事件。
    """

    def __init__(self):
        """
        初始化监控服务器事件回调接口
        """
        return

    def notify(self, level: str, msg: str):
        """
        通知事件回调
        
        @param level: 通知级别（字符串），如"info"、"warning"、"error"等
        @param msg: 通知消息内容（字符串）
        """
        return

from fastapi.middleware.cors import CORSMiddleware

class WtMonSvr(WatcherSink):
    """
    WonderTrader监控服务器类
    
    提供基于FastAPI的Web监控服务器，用于管理和监控WonderTrader交易系统。
    继承自WatcherSink，用于接收看门狗服务的事件。
    
    主要功能：
    1. 用户认证和权限管理：支持用户登录、权限验证、会话管理
    2. 组合管理：提供组合的增删改查、配置管理、状态查询等功能
    3. 策略管理：查询策略列表、策略数据（交易、资金、持仓等）
    4. 交易通道管理：查询交易通道的订单、成交、持仓、资金等信息
    5. 看门狗服务：管理应用的启动、停止、重启和监控
    6. 回测管理：集成回测管理器，提供回测任务的创建和管理
    7. 实时数据推送：通过WebSocket向客户端推送实时交易事件和日志
    8. 日志查询：查询系统日志和应用日志
    
    使用示例：
        sink = MySink()  # 自定义事件回调接口
        monSvr = WtMonSvr(static_folder="static/", deploy_dir="C:/", sink=sink)
        monSvr.run_as_server(port=8080, host="127.0.0.1")
    """

    def __init__(self, static_folder: str = "static/", deploy_dir="C:/", sink: WtMonSink = None, notifyTimeout:bool = True):
        """
        WtMonSvr构造函数
        
        初始化监控服务器，创建FastAPI应用、数据管理器、看门狗服务等组件。
        
        @param static_folder: 静态文件根目录（字符串，默认"static/"），包含前端页面文件的目录
        @param deploy_dir: 实盘部署目录（字符串，默认"C:/"），交易应用的部署根目录
        @param sink: 监控服务器事件回调接口（WtMonSink，默认None），用于处理服务器事件
        @param notifyTimeout: 是否启用超时通知（布尔值，默认True），True表示启用超时通知
        """

        # 创建日志记录器
        self.logger = WtLogger(__name__, "WtMonSvr.log")
        # 保存事件回调接口引用
        self._sink_ = sink

        # 数据管理器，主要用于缓存各组合的数据
        self.__data_mgr__ = DataMgr('data.db', logger=self.logger)

        # 回测管理器引用，初始化为None，可通过set_bt_mon方法设置
        self.__bt_mon__: WtBtMon = None
        # 数据服务器引用，初始化为None，可通过set_dt_servo方法设置
        self.__dt_servo__: WtDtServo = None

        # 秘钥和开启token访问，单独控制，减少依赖项
        # 如果启用token访问，需要安装pycryptodome库
        self.__sec_key__ = ""
        self.__token_enabled__ = False

        # 看门狗模块，主要用于调度各个组合启动关闭
        self._dog = WatchDog(sink=self, db=self.__data_mgr__.get_db(), logger=self.logger)

        # ========== 创建FastAPI应用 ==========
        # 创建FastAPI应用实例
        app = FastAPI(title="WtMonSvr", description="A http api of WtMonSvr", redoc_url=None, version="1.0.0")
        # 添加GZip压缩中间件，压缩大于1000字节的响应
        app.add_middleware(GZipMiddleware, minimum_size=1000)
        # 添加会话中间件，用于管理用户会话（会话超时时间为25200秒，即7小时）
        app.add_middleware(SessionMiddleware, secret_key='!@#$%^&*()', max_age=25200, session_cookie='WtMonSvr_sid')
        # 添加CORS中间件，允许跨域请求（允许所有来源、方法和请求头）
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 允许所有来源
            allow_credentials=True,  # 允许携带凭证
            allow_methods=["*"],  # 允许所有HTTP方法
            allow_headers=["*"])  # 允许所有请求头

        # ========== 挂载静态文件服务 ==========
        # 获取当前脚本所在目录
        script_dir = os.path.dirname(__file__)
        # 构建静态文件目录的完整路径
        static_folder = os.path.join(script_dir, static_folder)
        # 挂载控制台静态文件目录（/console路径）
        target_dir = os.path.join(static_folder,"console")
        app.mount("/console", StaticFiles(directory=target_dir), name="console")

        # 挂载移动端静态文件目录（/mobile路径）
        target_dir = os.path.join(static_folder,"mobile")
        app.mount("/mobile", StaticFiles(directory=target_dir), name="mobile")

        # ========== 保存实例变量 ==========
        self.app = app  # FastAPI应用实例
        self.worker = None  # 工作线程引用（用于后台运行）
        self.deploy_dir = deploy_dir  # 部署目录
        self.deploy_tree = None  # 部署目录树（用于文件浏览）
        self.static_folder = static_folder  # 静态文件目录
        self.notifyTimeout = notifyTimeout  # 是否启用超时通知

        # ========== 创建推送服务器 ==========
        # 创建WebSocket推送服务器，用于向客户端推送实时数据
        self.push_svr = PushServer(app, self.__data_mgr__, self.logger)

        # ========== 初始化API路由 ==========
        # 初始化管理API路由（组合管理、用户管理等）
        self.init_mgr_apis(app)
        # 初始化通用API路由（登录、日志查询等）
        self.init_comm_apis(app)

    def enable_token(self, seckey: str = "WtMonSvr@2021"):
        """
        启用访问令牌认证
        
        启用基于token的访问认证方式。启用后，客户端可以通过加密的token进行认证，
        而不需要依赖session。注意：启用token访问需要安装pycryptodome库。
        
        @param seckey: 加密密钥（字符串，默认"WtMonSvr@2021"），用于加密和解密token
        """
        # 设置加密密钥
        self.__sec_key__ = seckey
        # 启用token认证
        self.__token_enabled__ = True

    def set_bt_mon(self, btMon: WtBtMon):
        """
        设置回测管理器
        
        设置回测管理器实例，并初始化回测相关的API路由。
        
        @param btMon: 回测管理器WtBtMon实例，用于管理回测任务
        """
        # 保存回测管理器引用
        self.__bt_mon__ = btMon
        # 初始化回测API路由
        self.init_bt_apis(self.app)

    def set_dt_servo(self, dtServo: WtDtServo):
        """
        设置数据服务器
        
        设置数据服务器实例，用于提供历史数据查询服务。
        
        @param dtServo: 本地数据伺服WtDtServo实例，用于提供历史数据服务
        """
        # 保存数据服务器引用
        self.__dt_servo__ = dtServo

    def init_bt_apis(self, app: FastAPI):
        """
        初始化回测管理相关的API路由
        
        该方法注册所有与回测管理相关的HTTP API接口，包括：
        - K线数据查询：拉取历史K线数据用于回测
        - 策略管理：查询、添加、删除用户策略，获取和提交策略代码
        - 回测任务管理：启动策略回测、查询回测列表、删除回测任务
        - 回测结果查询：查询回测信号、成交、资金、回合等数据
        
        所有接口都需要用户认证，且仅限researcher和superman角色访问。
        部分接口需要配置数据伺服（dt_servo）和回测管理器（bt_mon）才能使用。
        
        @param app: FastAPI应用实例，用于注册路由
        """
        # 拉取K线数据
        @app.post("/bt/qrybars", tags=["回测管理接口"])
        async def qry_bt_bars(
            request: Request,
            token: str = Body(None, title="访问令牌", embed=True),
            code: str = Body(..., title="合约代码", embed=True),
            period: str = Body(..., title="K线周期", embed=True),
            stime: int = Body(None, title="开始时间", embed=True),
            etime: int = Body(..., title="结束时间", embed=True),
            count: int = Body(None, title="数据条数", embed=True)
        ):
            """
            查询回测K线数据接口
            
            从数据伺服中拉取指定合约的历史K线数据，用于回测分析。
            需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param code: 合约代码（必填），标准合约代码，如"SHFE.rb.HOT"
            @param period: K线周期（必填），如"m1"、"m5"、"d1"等
            @param stime: 开始时间（可选），格式为YYYYMMDD的整数，如20230101
            @param etime: 结束时间（必填），格式为YYYYMMDD的整数，如20231231
            @param count: 数据条数（可选），如果指定则返回最后N条数据
            @return: 包含result（结果码）、message（消息）、bars（K线数据列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查数据伺服是否已配置，如果未配置则无法查询数据
            if self.__dt_servo__ is None:
                # 构建数据伺服未配置的错误响应
                ret = {
                    "result": -2,  # 错误码：数据伺服未配置
                    "message": "没有配置数据伺服"
                }
                return ret

            # 将合约代码赋值给标准代码变量
            stdCode = code
            # 将开始时间赋值给fromTime变量
            fromTime = stime
            # 将数据条数赋值给dataCount变量
            dataCount = count
            # 将结束时间赋值给endTime变量
            endTime = etime

            # 调用数据伺服的get_bars方法获取K线数据
            bars = self.__dt_servo__.get_bars(stdCode=stdCode, period=period, fromTime=fromTime, dataCount=dataCount,
                                              endTime=endTime)
            # 如果返回的K线数据为空，说明没有找到数据
            if bars is None:
                # 构建数据未找到的错误响应
                ret = {
                    "result": -2,  # 错误码：数据未找到
                    "message": "Data not found"
                }
            else:
                # 将K线对象列表转换为字典列表，方便JSON序列化
                bar_list = [curBar.to_dict for curBar in bars]

                # 构建成功响应，包含K线数据列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "bars": bar_list  # K线数据列表
                }

            # 返回响应结果
            return ret

        # 拉取用户策略列表
        @app.post("/bt/qrystras", tags=["回测管理接口"])
        @app.get("/bt/qrystras", tags=["回测管理接口"])
        async def qry_my_stras(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询用户策略列表接口
            
            获取当前用户的所有回测策略列表。支持GET和POST两种请求方式。
            需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、strategies（策略列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 构建成功响应，调用回测管理器的get_strategies方法获取用户策略列表
            ret = {
                "result": 0,  # 成功码
                "message": "OK",
                "strategies": self.__bt_mon__.get_strategies(user)  # 策略列表
            }

            # 返回响应结果
            return ret

        # 拉取策略代码
        @app.post("/bt/qrycode", tags=["回测管理接口"])
        async def qry_stra_code(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询策略代码接口
            
            获取指定策略的源代码内容。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、content（策略代码内容）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略代码不存在"
                    }
                else:
                    # 调用回测管理器获取策略代码内容
                    content = self.__bt_mon__.get_strategy_code(user, straid)
                    # 构建成功响应，包含策略代码内容
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "content": content  # 策略代码内容
                    }

            # 返回响应结果
            return ret

        # 提交策略代码
        @app.post("/bt/setcode", tags=["回测管理接口"])
        def set_stra_code(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
                content: str = Body(..., title="策略代码", embed=True)
        ):
            """
            提交策略代码接口
            
            保存或更新指定策略的源代码内容。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要保存的策略标识符
            @param content: 策略代码（必填），策略的源代码内容
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID和代码内容是否为空
            if len(content) == 0 or len(straid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID和代码不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 调用回测管理器保存策略代码，返回保存是否成功
                    ret = self.__bt_mon__.set_strategy_code(user, straid, content)
                    # 如果保存成功
                    if ret:
                        # 构建成功响应
                        ret = {
                            "result": 0,  # 成功码
                            "message": "OK"
                        }
                    else:
                        # 构建保存失败的错误响应
                        ret = {
                            "result": -3,  # 错误码：保存失败
                            "message": "保存策略代码失败"
                        }

            # 返回响应结果
            return ret

        # 添加用户策略
        @app.post("/bt/addstra", tags=["回测管理接口"])
        async def cmd_add_stra(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                name: str = Body(..., title="策略名称", embed=True)
        ):
            """
            添加用户策略接口
            
            为用户创建一个新的回测策略。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param name: 策略名称（必填），新策略的显示名称
            @return: 包含result（结果码）、message（消息）、strategy（策略信息，可选）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略名称是否为空
            if len(name) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略名称不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -3,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
                return ret

            # 调用回测管理器添加策略，返回策略信息
            straInfo = self.__bt_mon__.add_strategy(user, name)
            # 如果添加失败（返回None）
            if straInfo is None:
                # 构建添加失败的错误响应
                ret = {
                    "result": -4,  # 错误码：添加失败
                    "message": "策略添加失败"
                }
            else:
                # 构建成功响应，包含策略信息
                ret = {
                    "result": 0,  # 成功码
                    "message": "OK",
                    "strategy": straInfo  # 策略信息（包含策略ID、名称等）
                }

            # 返回响应结果
            return ret

        # 删除用户策略
        @app.post("/bt/delstra", tags=["回测管理接口"])
        async def cmd_del_stra(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            删除用户策略接口
            
            删除指定用户的回测策略及其相关数据。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要删除的策略标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID是否为空
            if len(straid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 调用回测管理器删除策略，返回删除是否成功
                    ret = self.__bt_mon__.del_strategy(user, straid)
                    # 如果删除成功
                    if ret:
                        # 构建成功响应
                        ret = {
                            "result": 0,  # 成功码
                            "message": "OK"
                        }
                    else:
                        # 构建删除失败的错误响应
                        ret = {
                            "result": -3,  # 错误码：删除失败
                            "message": "保存策略代码失败"
                        }

            # 返回响应结果
            return ret

        # 获取策略回测列表
        @app.post("/bt/qrystrabts", tags=["回测管理接口"])
        async def qry_stra_bts(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
        ):
            """
            查询策略回测列表接口
            
            获取指定策略的所有回测任务列表。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、backtests（回测列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID是否为空
            if len(straid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 构建成功响应，调用回测管理器获取策略的回测列表
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "backtests": self.__bt_mon__.get_backtests(user, straid)  # 回测列表
                    }

            # 返回响应结果
            return ret

        # 获取策略回测信号
        @app.post("/bt/qrybtsigs", tags=["回测管理接口"])
        async def qry_stra_bt_signals(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
                btid: str = Body(..., title="回测ID", embed=True)
        ):
            """
            查询策略回测信号接口
            
            获取指定回测任务中策略产生的所有交易信号。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要查询的策略标识符
            @param btid: 回测ID（必填），要查询的回测任务标识符
            @return: 包含result（结果码）、message（消息）、signals（信号列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID和回测ID是否为空
            if len(straid) == 0 or len(btid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID和回测ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 构建成功响应，调用回测管理器获取回测信号列表
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "signals": self.__bt_mon__.get_bt_signals(user, straid, btid)  # 信号列表
                    }

            # 返回响应结果
            return ret

        # 删除策略回测列表
        @app.post("/bt/delstrabt", tags=["回测管理接口"])
        async def cmd_del_stra_bt(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                btid: str = Body(..., title="回测ID", embed=True)
        ):
            """
            删除策略回测任务接口
            
            删除指定的回测任务及其相关数据。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param btid: 回测ID（必填），要删除的回测任务标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查回测ID是否为空
            if len(btid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "回测ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 调用回测管理器删除回测任务
                self.__bt_mon__.del_backtest(user, btid)
                # 构建成功响应
                ret = {
                    "result": 0,  # 成功码
                    "message": "OK"
                }

            # 返回响应结果
            return ret

        # 获取策略回测成交
        @app.post("/bt/qrybttrds", tags=["回测管理接口"])
        async def qry_stra_bt_trades(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
                btid: str = Body(..., title="回测ID", embed=True)
        ):
            """
            查询策略回测成交接口
            
            获取指定回测任务中策略产生的所有成交记录。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要查询的策略标识符
            @param btid: 回测ID（必填），要查询的回测任务标识符
            @return: 包含result（结果码）、message（消息）、trades（成交列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID和回测ID是否为空
            if len(straid) == 0 or len(btid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID和回测ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 构建成功响应，调用回测管理器获取回测成交列表
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "trades": self.__bt_mon__.get_bt_trades(user, straid, btid)  # 成交列表
                    }

            # 返回响应结果
            return ret

        # 获取策略回测资金
        @app.post("/bt/qrybtfunds", tags=["回测管理接口"])
        async def qry_stra_bt_funds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
                btid: str = Body(..., title="回测ID", embed=True)
        ):
            """
            查询策略回测资金接口
            
            获取指定回测任务中策略的资金曲线数据。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要查询的策略标识符
            @param btid: 回测ID（必填），要查询的回测任务标识符
            @return: 包含result（结果码）、message（消息）、funds（资金曲线数据）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID和回测ID是否为空
            if len(straid) == 0 or len(btid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID和回测ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 构建成功响应，调用回测管理器获取回测资金曲线数据
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "funds": self.__bt_mon__.get_bt_funds(user, straid, btid)  # 资金曲线数据
                    }

            # 返回响应结果
            return ret

        # 获取策略回测回合
        @app.post("/bt/qrybtrnds", tags=["回测管理接口"])
        async def qry_stra_bt_rounds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
                btid: str = Body(..., title="回测ID", embed=True)
        ):
            """
            查询策略回测回合接口
            
            获取指定回测任务中策略的所有交易回合记录。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要查询的策略标识符
            @param btid: 回测ID（必填），要查询的回测任务标识符
            @return: 包含result（结果码）、message（消息）、rounds（回合列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 检查策略ID和回测ID是否为空
            if len(straid) == 0 or len(btid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID和回测ID不能为空"
                }
                return ret

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 构建成功响应，调用回测管理器获取回测回合列表
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "rounds": self.__bt_mon__.get_bt_rounds(user, straid, btid)  # 回合列表
                    }

            # 返回响应结果
            return ret

        # 启动策略回测
        @app.post("/bt/runstrabt", tags=["回测管理接口"])
        def cmd_run_stra_bt(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                straid: str = Body(..., title="策略ID", embed=True),
                stime: int = Body(None, title="开始时间", embed=True),
                etime: int = Body(None, title="结束时间", embed=True),
                capital: int = Body(500000, title="本金", embed=True),
                slippage: int = Body(0, title="滑点", embed=True)
        ):
            """
            启动策略回测接口
            
            启动指定策略的回测任务，使用指定的时间范围和参数进行回测。需要用户认证，且仅限researcher和superman角色访问。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param straid: 策略ID（必填），要回测的策略标识符
            @param stime: 开始时间（可选），格式为YYYYMMDD的整数，如20230101
            @param etime: 结束时间（可选），格式为YYYYMMDD的整数，如20231231
            @param capital: 本金（可选，默认500000），回测的初始资金
            @param slippage: 滑点（可选，默认0），回测时的滑点设置（单位：最小变动价位）
            @return: 包含result（结果码）、message（消息）、backtest（回测信息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo

            # 从用户信息中提取登录ID
            user = userInfo["loginid"]
            # 从用户信息中提取用户角色
            role = userInfo["role"]
            # 检查用户角色是否为researcher或superman，只有这两个角色可以访问回测接口
            if role not in ['researcher', 'superman']:
                # 构建权限不足的错误响应
                ret = {
                    "result": -1,  # 错误码：权限不足
                    "message": "没有权限"
                }
                return ret

            # 获取当前日期（格式：YYYYMMDD），用于后续处理（虽然当前未使用）
            curDt = int(datetime.datetime.now().strftime("%Y%m%d"))
            # 将开始时间赋值给fromtime变量
            fromtime = stime
            # 将结束时间赋值给endtime变量
            endtime = etime

            # 检查策略ID是否为空
            if len(straid) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -2,  # 错误码：参数错误
                    "message": "策略ID不能为空"
                }
                return ret

            # 如果开始时间大于结束时间，交换两者（确保时间范围有效）
            if fromtime > endtime:
                fromtime, endtime = endtime, fromtime

            # 将日期转换为时间戳格式：YYYYMMDD * 10000 + HHMM
            # 开始时间设置为当天的09:00（900表示09:00）
            fromtime = fromtime * 10000 + 900
            # 结束时间设置为当天的15:15（1515表示15:15）
            endtime = endtime * 10000 + 1515

            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建回测管理器未配置的错误响应
                ret = {
                    "result": -1,  # 错误码：回测管理器未配置
                    "message": "回测管理器未配置"
                }
            else:
                # 检查策略是否存在
                if not self.__bt_mon__.has_strategy(user, straid):
                    # 构建策略不存在的错误响应
                    ret = {
                        "result": -2,  # 错误码：策略不存在
                        "message": "策略不存在"
                    }
                else:
                    # 调用回测管理器启动回测任务，返回回测信息
                    btInfo = self.__bt_mon__.run_backtest(user, straid, fromtime, endtime, capital, slippage)
                    # 构建成功响应，包含回测信息
                    ret = {
                        "result": 0,  # 成功码
                        "message": "OK",
                        "backtest": btInfo  # 回测信息（包含回测ID、状态等）
                    }

            # 返回响应结果
            return ret

    def init_mgr_apis(self, app: FastAPI):
        """
        初始化管理相关的API路由
        
        该方法注册所有与系统管理相关的HTTP API接口，包括：
        
        1. 用户管理接口：
           - 用户登录、修改密码
           - 用户列表查询、添加、删除、重置密码
           - 操作记录查询
        
        2. 策略组管理接口：
           - 组合的增删改查、启动停止
           - 组合配置、文件管理（查询、提交）
           - 组合目录结构查询
           - 策略列表、通道列表查询
           - 组合日志查询
        
        3. 策略管理接口：
           - 策略成交、信号、回合、持仓、资金查询
        
        4. 交易通道管理接口：
           - 通道订单、成交、持仓、资金查询
        
        5. 组合盘管理接口：
           - 组合持仓、成交、回合、资金查询
           - 组合绩效分析、过滤器管理
        
        6. 调度器管理接口：
           - 调度任务查询、启动、停止、删除
           - 监控配置查询和设置
           - 调度日志查询
        
        7. 通用接口：
           - Python执行路径查询
           - 部署目录结构查询
        
        8. 令牌认证接口：
           - 令牌验证和用户信息获取
        
        所有接口都需要用户认证，部分接口需要管理员权限。
        
        @param app: FastAPI应用实例，用于注册路由
        """

        @app.post("/mgr/login", tags=["用户接口"])
        async def cmd_login(
            request: Request,
            loginid: str = Body(..., title="用户名", embed=True),
            passwd: str = Body(..., title="用户密码", embed=True)
        ):
            """
            用户登录接口
            
            验证用户身份并创建会话。登录成功后会在session中保存token信息，
            如果启用了token认证，还会返回加密的token供客户端使用。
            
            @param request: FastAPI请求对象
            @param loginid: 用户名（必填），用户登录名
            @param passwd: 用户密码（必填），明文密码
            @return: 包含result（结果码）、message（消息）、userinfo（用户信息）、token（可选，加密令牌）的字典
            """
            if True:
                # 将登录ID赋值给user变量
                user = loginid
                # 将密码赋值给pwd变量
                pwd = passwd

                # 检查用户名和密码是否为空
                if len(user) == 0 or len(pwd) == 0:
                    # 构建参数为空的错误响应
                    ret = {
                        "result": -1,  # 错误码：参数错误
                        "message": "用户名和密码不能为空"
                    }
                else:
                    # 使用MD5加密密码：将用户名和密码拼接后计算MD5哈希值
                    encpwd = hashlib.md5((user + pwd).encode("utf-8")).hexdigest()
                    # 获取当前时间
                    now = datetime.datetime.now()
                    # 从数据管理器中获取用户信息
                    usrInf = self.__data_mgr__.get_user(user)
                    # 检查用户是否存在以及密码是否正确
                    if usrInf is None or encpwd != usrInf["passwd"]:
                        # 构建用户名或密码错误的响应
                        ret = {
                            "result": -1,  # 错误码：认证失败
                            "message": "用户名或密码错误"
                        }
                    else:
                        # 从用户信息中移除密码字段，避免泄露
                        usrInf.pop("passwd")
                        # 记录用户登录IP地址
                        usrInf["loginip"] = request.client.host
                        # 记录用户登录时间，格式化为字符串
                        usrInf["logintime"] = now.strftime("%Y/%m/%d %H:%M:%S")
                        # 获取用户可访问的产品列表
                        products = usrInf["products"]

                        # 计算token过期时间：当前时间加360分钟（6小时）
                        exptime = now + datetime.timedelta(minutes=360)  # 360分钟令牌超时
                        # 构建token信息字典，包含用户身份和权限信息
                        tokenInfo = {
                            "loginid": user,  # 登录ID
                            "role": usrInf["role"],  # 用户角色
                            "logintime": now.strftime("%Y/%m/%d %H:%M:%S"),  # 登录时间
                            "expiretime": exptime.replace(tzinfo=pytz.timezone('UTC')).strftime("%Y.%m.%d %H:%M:%S"),  # 过期时间（UTC时区）
                            "products": products,  # 可访问的产品列表
                            "loginip": request.client.host  # 登录IP
                        }
                        # 将token信息保存到session中
                        set_session(request, "tokeninfo", tokenInfo)

                        # 如果启用了token认证，生成加密的token返回给客户端
                        if self.__token_enabled__:
                            # 使用AES加密token信息，转换为JSON字符串后加密
                            token = AES_Encrypt(self.__sec_key__, json.dumps(tokenInfo))
                            # 构建成功响应，包含用户信息和加密token
                            ret = {
                                "result": 0,  # 成功码
                                "message": "Ok",
                                "userinfo": usrInf,  # 用户信息（不包含密码）
                                "token": token  # 加密的token
                            }
                        else:
                            # 如果未启用token认证，只返回用户信息
                            ret = {
                                "result": 0,  # 成功码
                                "message": "Ok",
                                "userinfo": usrInf  # 用户信息（不包含密码）
                            }

                        # 记录用户登录操作日志，包含User-Agent信息
                        self.__data_mgr__.log_action(usrInf, "login", json.dumps(request.headers.get('User-Agent')))
            else:
                # 如果请求处理出现异常（此分支通常不会执行）
                ret = {
                    "result": -1,  # 错误码：处理异常
                    "message": "请求处理出现异常",
                }
                # 如果session中存在userinfo，清除它
                if get_session(request, "userinfo") is not None:
                    pop_session("userinfo")

            # 返回响应结果
            return ret

        # 修改密码
        @app.post("/mgr/modpwd", tags=["用户接口"])
        async def mod_pwd(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                oldpwd: str = Body(..., title="旧密码", embed=True),
                newpwd: str = Body(..., title="新密码", embed=True)
        ):
            """
            修改用户密码接口
            
            用户修改自己的登录密码。需要提供旧密码进行验证。
            如果用户是内建账户，会先将其添加到数据库中。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param oldpwd: 旧密码（必填），当前使用的密码
            @param newpwd: 新密码（必填），要设置的新密码
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 检查旧密码和新密码是否为空
            if len(oldpwd) == 0 or len(newpwd) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -1,  # 错误码：参数错误
                    "message": "新旧密码都不能为空"
                }
            else:
                # 从认证信息中获取登录ID
                user = adminInfo["loginid"]
                # 使用MD5加密旧密码：将用户名和旧密码拼接后计算MD5哈希值
                oldencpwd = hashlib.md5((user + oldpwd).encode("utf-8")).hexdigest()
                # 从数据管理器中获取用户信息
                usrInf = self.__data_mgr__.get_user(user)
                # 检查用户是否存在
                if usrInf is None:
                    # 构建用户不存在的错误响应
                    ret = {
                        "result": -1,  # 错误码：用户不存在
                        "message": "用户不存在"
                    }
                else:
                    # 验证旧密码是否正确
                    if oldencpwd != usrInf["passwd"]:
                        # 构建旧密码错误的响应
                        ret = {
                            "result": -1,  # 错误码：密码错误
                            "message": "旧密码错误"
                        }
                    else:
                        # 如果用户是内建账户（builtin标志为True），需要先将其添加到数据库中
                        if 'builtin' in usrInf and usrInf["builtin"]:
                            # 设置用户密码为旧密码（明文），用于添加到数据库
                            usrInf["passwd"] = oldpwd
                            # 将内建用户添加到数据库中
                            self.__data_mgr__.add_user(usrInf, user)
                            # 输出日志信息
                            print("%s是内建账户，自动添加到数据库中" % user)

                        # 使用MD5加密新密码：将用户名和新密码拼接后计算MD5哈希值
                        newencpwd = hashlib.md5((user + newpwd).encode("utf-8")).hexdigest()
                        # 修改用户密码，传入用户名、加密后的新密码和操作者
                        self.__data_mgr__.mod_user_pwd(user, newencpwd, user)

                        # 构建成功响应
                        ret = {
                            "result": 0,  # 成功码
                            "message": "Ok"
                        }

            # 返回响应结果
            return ret

        # 添加组合
        @app.post("/mgr/addgrp", tags=["策略组管理接口"])
        async def cmd_add_group(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                name: str = Body('', title="组合名称", embed=True),
                path: str = Body('', title="组合路径", embed=True),
                gtype: str = Body('', title="组合类型", embed=True),
                info: str = Body('', title="组合信息",embed=True),
                env: str = Body('', title="组合环境，实盘/回测", embed=True),
                datmod: str = Body('mannual', title="数据模式，mannal/auto", embed=True),
                mqurl: str = Body('', title="消息队列地址", embed=True),
                action: str = Body('add', title="操作类型，add/mod", embed=True)
        ):
            """
            添加或修改组合接口
            
            添加新的策略组合或修改现有组合的配置信息。
            组合是策略运行的容器，包含策略配置、执行器配置等信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），组合的唯一标识符
            @param name: 组合名称（可选，默认空字符串），组合的显示名称
            @param path: 组合路径（可选，默认空字符串），组合配置文件的目录路径
            @param gtype: 组合类型（可选，默认空字符串），组合的类型标识
            @param info: 组合信息（可选，默认空字符串），组合的备注信息
            @param env: 组合环境（可选，默认空字符串），"实盘"或"回测"
            @param datmod: 数据模式（可选，默认"mannual"），"mannual"（手动）或"auto"（自动）
            @param mqurl: 消息队列地址（可选，默认空字符串），用于接收组合事件的消息队列URL
            @param action: 操作类型（可选，默认"add"），"add"（添加）或"mod"（修改）
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将组合ID赋值给id变量
            id = groupid

            # 如果操作类型为空，默认为"add"（添加）
            if action == "":
                action = "add"

            # 检查组合ID、名称、类型是否为空
            if len(id) == 0 or len(name) == 0 or len(gtype) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -1,  # 错误码：参数错误
                    "message": "组合ID、名称、类型都不能为空"
                }
            # 检查组合路径是否存在且为目录
            elif not os.path.exists(path) or not os.path.isdir(path):
                # 构建路径不正确的错误响应
                ret = {
                    "result": -2,  # 错误码：路径错误
                    "message": "组合运行目录不正确"
                }
            # 如果是添加操作且组合ID已存在，返回重复错误
            elif action == "add" and self.__data_mgr__.has_group(id):
                # 构建组合ID重复的错误响应
                ret = {
                    "result": -3,  # 错误码：ID重复
                    "message": "组合ID不能重复"
                }
            else:
                try:
                    # 构建组合信息字典
                    grpInfo = {
                        "id": id,  # 组合ID
                        "name": name,  # 组合名称
                        "path": path,  # 组合路径
                        "info": info,  # 组合信息
                        "gtype": gtype,  # 组合类型
                        "datmod": datmod,  # 数据模式
                        "env": env,  # 组合环境
                        "mqurl": mqurl  # 消息队列地址
                    }

                    # 调用数据管理器添加组合
                    if self.__data_mgr__.add_group(grpInfo):
                        # 构建成功响应
                        ret = {
                            "result": 0,  # 成功码
                            "message": "Ok"
                        }

                        # 根据操作类型记录操作日志
                        if action == "add":
                            # 记录添加组合的操作日志
                            self.__data_mgr__.log_action(adminInfo, "addgrp", json.dumps(grpInfo))
                        else:
                            # 记录修改组合的操作日志
                            self.__data_mgr__.log_action(adminInfo, "modgrp", json.dumps(grpInfo))

                        # 更新看门狗服务中的消息队列URL
                        self._dog.updateMQURL(id, mqurl)
                    else:
                        # 构建添加失败的错误响应
                        ret = {
                            "result": -2,  # 错误码：添加失败
                            "message": "添加用户失败"
                        }
                except:
                    # 捕获所有异常，构建请求解析失败的错误响应
                    ret = {
                        "result": -1,  # 错误码：解析失败
                        "message": "请求解析失败"
                    }

            # 返回响应结果
            return ret

        # 删除组合
        @app.post("/mgr/delgrp", tags=["策略组管理接口"])
        async def cmd_del_group(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            删除组合接口
            
            删除指定的策略组合及其相关配置。删除前需要先停止组合的运行。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要删除的组合标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将组合ID赋值给id变量
            id = groupid

            # 检查组合ID是否为空
            if len(id) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -1,  # 错误码：参数错误
                    "message": "组合ID不能为空"
                }
            # 检查组合是否存在
            elif not self.__data_mgr__.has_group(id):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -3,  # 错误码：组合不存在
                    "message": "该组合不存在"
                }
            # 检查组合是否正在运行，如果正在运行则不能删除
            elif self._dog.isRunning(id):
                # 构建组合正在运行的错误响应
                ret = {
                    "result": -3,  # 错误码：组合正在运行
                    "message": "请先停止该组合"
                }
            else:
                if True:
                    # 从看门狗服务中删除应用配置
                    self._dog.delApp(id)
                    # 从数据管理器中删除组合
                    self.__data_mgr__.del_group(id)
                    # 构建成功响应
                    ret = {
                        "result": 0,  # 成功码
                        "message": "Ok"
                    }

                    # 记录删除组合的操作日志
                    self.__data_mgr__.log_action(adminInfo, "delgrp", id)
                else:
                    # 如果请求处理出现异常（此分支通常不会执行）
                    ret = {
                        "result": -1,  # 错误码：处理异常
                        "message": "请求解析失败"
                    }

            # 返回响应结果
            return ret

        # 组合停止
        @app.post("/mgr/stopgrp", tags=["策略组管理接口"])
        async def cmd_stop_group(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            停止组合接口
            
            停止指定组合的运行。如果组合正在运行，则停止它；如果已经停止，则直接返回成功。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要停止的组合标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 如果组合正在运行，调用看门狗服务停止它
                if self._dog.isRunning(grpid):
                    self._dog.stop(grpid)
                # 构建成功响应
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok"
                }

                # 记录停止组合的操作日志
                self.__data_mgr__.log_action(adminInfo, "stopgrp", grpid)

            # 返回响应结果
            return ret

        # 组合启动
        @app.post("/mgr/startgrp", tags=["策略组管理接口"])
        async def cmd_start_group(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            启动组合接口
            
            启动指定组合的运行。如果组合未运行，则启动它；如果已经运行，则直接返回成功。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要启动的组合标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 如果组合未运行，调用看门狗服务启动它
                if not self._dog.isRunning(grpid):
                    self._dog.start(grpid)
                # 构建成功响应
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok"
                }
                # 记录启动组合的操作日志
                self.__data_mgr__.log_action(adminInfo, "startgrp", grpid)

            # 返回响应结果
            return ret

        # 获取执行的python进程的路径
        @app.post("/mgr/qryexec", tags=["通用接口"])
        def qry_exec_path(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询Python执行路径接口
            
            获取当前Python解释器的可执行文件路径。用于确定运行环境。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、path（Python可执行文件路径）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 构建成功响应，包含Python可执行文件路径
            ret = {
                "result": 0,  # 成功码
                "message": "Ok",
                "path": sys.executable  # Python解释器的可执行文件路径
            }
            # 返回响应结果
            return ret

        # 配置监控
        @app.post("/mgr/qrymon", tags=["调度器管理接口"])
        async def qry_mon_cfg(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询监控配置接口
            
            获取指定组合的看门狗监控配置信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、config（监控配置，可选）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 从看门狗服务获取应用的监控配置
                monCfg = self._dog.getAppConf(grpid)
                # 如果配置不存在
                if monCfg is None:
                    # 构建成功响应（无配置信息）
                    ret = {
                        "result": 0,  # 成功码
                        "message": "ok"
                    }
                else:
                    # 构建成功响应，包含监控配置信息
                    ret = {
                        "result": 0,  # 成功码
                        "message": "ok",
                        "config": monCfg  # 监控配置信息
                    }

            # 返回响应结果
            return ret

        # 配置监控
        @app.post("/mgr/cfgmon", tags=["调度器管理接口"])
        async def cmd_config_monitor(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                config: dict = Body(..., title="监控配置", embed=True)
        ):
            """
            配置监控接口
            
            设置看门狗服务的监控配置。可以配置单个应用或整个组合的监控参数。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param config: 监控配置（必填），包含监控参数的字典
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 检查配置中是否包含"group"字段，用于判断是否为组合配置
            # 这里本来是要做检查的，算了，先省事吧
            isGrp = False
            # 如果配置中包含"group"字段，获取其值
            if "group" in config:
                isGrp = config["group"]

            # 应用监控配置到看门狗服务，isGrp表示是否为组合配置
            self._dog.applyAppConf(config, isGrp)
            # 构建成功响应
            ret = {
                "result": 0,  # 成功码
                "message": "ok"
            }
            # 记录配置监控的操作日志
            self.__data_mgr__.log_action(adminInfo, "cfgmon", json.dumps(config))

            # 返回响应结果
            return ret

        # 查询目录结构
        @app.post("/mgr/qrydir", tags=["通用接口"])
        async def qry_directories(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询部署目录结构接口
            
            获取部署目录的树形结构，用于文件浏览和管理。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、tree（目录树结构）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            if True:
                # 如果部署目录树未缓存，则生成目录树
                if self.deploy_tree is None:
                    # 调用get_path_tree函数生成部署目录的树形结构
                    self.deploy_tree = get_path_tree(self.deploy_dir, "root")

                # 构建成功响应，包含目录树结构
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "tree": self.deploy_tree  # 目录树结构
                }
            else:
                # 如果请求处理出现异常（此分支通常不会执行）
                ret = {
                    "result": -1,  # 错误码：处理异常
                    "message": "请求解析失败"
                }

            # 返回响应结果
            return ret

        # 查询目录结构
        @app.post("/mgr/qrygrpdir", tags=["策略组管理接口"])
        async def qry_grp_directories(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合目录结构接口
            
            获取指定组合的配置文件目录树形结构，包括run.py、config.json/config.yaml等配置文件。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、tree（配置文件目录树结构）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 从数据管理器获取组合信息
                monCfg = self.__data_mgr__.get_group(grpid)

                # 构建成功响应，调用get_cfg_tree函数生成组合配置文件的目录树结构
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "tree": get_cfg_tree(monCfg["path"], "root")  # 配置文件目录树结构
                }

            # 返回响应结果
            return ret

        # 查询组合列表
        @app.post("/mgr/qrygrp", tags=["策略组管理接口"])
        @app.get("/mgr/qrygrp", tags=["策略组管理接口"])
        async def qry_groups(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询组合列表接口
            
            获取所有策略组合的列表。支持GET和POST两种请求方式。
            根据用户的产品权限过滤组合，只返回用户有权限访问的组合。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、groups（组合列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, tokenInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return tokenInfo

            # 从用户信息中获取用户可访问的产品列表
            products = tokenInfo["products"]
            
            try:
                # 从数据管理器获取所有组合列表
                groups = self.__data_mgr__.get_groups()
                # 初始化返回的组合列表
                rets = list()
                # 遍历所有组合
                for grpInfo in groups:
                    # 如果用户没有产品限制（products为空）或组合ID在用户的产品列表中
                    if len(products) == 0 or grpInfo["id"] in products:
                        # 添加组合的运行状态信息
                        grpInfo["running"] = self._dog.isRunning(grpInfo["id"])
                        # 将组合信息添加到返回列表
                        rets.append(grpInfo)

                # 构建成功响应，包含过滤后的组合列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "groups": rets  # 组合列表（包含运行状态）
                }
            except:
                # 捕获所有异常，构建请求解析失败的错误响应
                ret = {
                    "result": -1,  # 错误码：处理异常
                    "message": "请求解析失败"
                }

            # 返回响应结果
            return ret

        # 查询文件信息
        @app.post("/mgr/qrygrpfile", tags=["策略组管理接口"])
        async def qry_group_file(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                path: str = Body(..., title="文件路径", embed=True),
        ):
            """
            查询组合文件内容接口
            
            读取指定组合目录下的文件内容。会检查文件路径是否在组合目录下，确保安全性。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），文件所属的组合标识符
            @param path: 文件路径（必填），要读取的文件完整路径
            @return: 包含result（结果码）、message（消息）、content（文件内容）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 从数据管理器获取组合信息
                monCfg = self.__data_mgr__.get_group(grpid)
                # 获取组合的根路径
                root = monCfg["path"]
                # 检查文件路径是否在组合目录下（安全检查）
                if path[:len(root)] != root:
                    # 构建路径不在组合下的错误响应
                    ret = {
                        "result": -1,  # 错误码：路径错误
                        "message": "目标文件不在当前组合下"
                    }
                else:
                    # 以二进制模式打开文件
                    f = open(path, 'rb')
                    # 读取文件内容
                    content = f.read()
                    # 关闭文件
                    f.close()

                    # 使用chardet检测文件编码
                    encoding = chardet.detect(content)["encoding"]
                    # 使用检测到的编码解码文件内容
                    content = content.decode(encoding)

                    # 构建成功响应，包含文件内容
                    ret = {
                        "result": 0,  # 成功码
                        "message": "Ok",
                        "content": content  # 文件内容（文本）
                    }

            # 返回响应结果
            return ret

        # 提交组合文件
        @app.post("/mgr/cmtgrpfile", tags=["策略组管理接口"])
        async def cmd_commit_group_file(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                path: str = Body(..., title="文件路径", embed=True),
                content: str = Body(..., title="文件内容", embed=True)
        ):
            """
            提交组合文件接口
            
            保存或更新指定组合目录下的文件内容。保存前会先备份原文件，然后使用原文件的编码保存新内容。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），文件所属的组合标识符
            @param path: 文件路径（必填），要保存的文件完整路径
            @param content: 文件内容（必填），要保存的文件内容（文本）
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 从数据管理器获取组合信息
                monCfg = self.__data_mgr__.get_group(grpid)
                # 获取组合的根路径
                root = monCfg["path"]
                # 检查文件路径是否在组合目录下（安全检查）
                if path[:len(root)] != root:
                    # 构建路径不在组合下的错误响应
                    ret = {
                        "result": -1,  # 错误码：路径错误
                        "message": "目标文件不在当前组合下"
                    }
                else:
                    try:
                        # 以二进制模式打开原文件
                        f = open(path, 'rb')
                        # 读取原文件内容
                        old_content = f.read()
                        # 关闭文件
                        f.close()
                        # 使用chardet检测原文件的编码
                        encoding = chardet.detect(old_content)["encoding"]

                        # 备份原文件（创建.bak备份文件）
                        backup_file(path)

                        # 以二进制模式打开文件准备写入
                        f = open(path, 'wb')
                        # 使用原文件的编码将新内容编码后写入文件
                        f.write(content.encode(encoding))
                        # 关闭文件
                        f.close()

                        # 构建成功响应
                        ret = {
                            "result": 0,  # 成功码
                            "message": "Ok"
                        }
                    except:
                        # 捕获所有异常，构建文件保存失败的错误响应
                        ret = {
                            "result": -1,  # 错误码：保存失败
                            "message": "文件保存失败"
                        }

            # 返回响应结果
            return ret

        # 查询策略列表
        @app.post("/mgr/qrystras", tags=["策略组管理接口"])
        async def qry_strategys(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询策略列表接口
            
            获取指定组合中的所有策略列表。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、strategies（策略列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取策略列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "strategies": self.__data_mgr__.get_strategies(grpid)  # 策略列表
                }

            # 返回响应结果
            return ret

        # 查询通道列表
        @app.post("/mgr/qrychnls", tags=["策略组管理接口"])
        async def qry_channels(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询通道列表接口
            
            获取指定组合中的所有交易通道列表。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、channels（通道列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取通道列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "channels": self.__data_mgr__.get_channels(grpid)  # 通道列表
                }

            # 返回响应结果
            return ret

        # 查询组合日志
        @app.post("/mgr/qrylogs", tags=["策略组管理接口"])
        async def qry_logs(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                id: str = Body(..., title="组合ID", embed=True),
                type: str = Body(..., title="日志类型", embed=True),
        ):
            """
            查询组合日志接口
            
            获取指定组合的最新日志内容。读取组合Logs目录下最新的Runner日志文件的最后100行。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param id: 组合ID（必填），要查询的组合标识符
            @param type: 日志类型（必填），日志类型标识（当前未使用）
            @return: 包含result（结果码）、message（消息）、content（日志内容）、lines（行数）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = id
            # 将日志类型赋值给logtype变量（当前未使用）
            logtype = type

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 从数据管理器获取组合信息
                grpInfo = self.__data_mgr__.get_group(grpid)
                try:
                    # 构建日志文件夹路径
                    logfolder = os.path.join(grpInfo["path"], "./Logs/")
                    # 获取日志文件夹中的所有文件列表
                    file_list = os.listdir(logfolder)
                    # 初始化目标文件列表
                    targets = list()
                    # 遍历所有文件，筛选出Runner开头的日志文件
                    for fname in file_list:
                        if fname[:6] == "Runner":
                            targets.append(fname)

                    # 对目标文件列表进行排序
                    targets.sort()
                    # 获取最新的日志文件路径（排序后的最后一个）
                    filename = os.path.join(logfolder, targets[-1])
                    # 读取日志文件的最后100行
                    content, lines = get_tail(filename, 100)
                    # 构建成功响应，包含日志内容和行数
                    ret = {
                        "result": 0,  # 成功码
                        "message": "Ok",
                        "content": content,  # 日志内容（最后100行）
                        "lines": lines  # 实际读取的行数
                    }
                except:
                    # 捕获所有异常，构建请求解析失败的错误响应
                    ret = {
                        "result": -1,  # 错误码：处理异常
                        "message": "请求解析失败"
                    }

            # 返回响应结果
            return ret

        # 查询策略成交
        @app.post("/mgr/qrytrds", tags=["策略管理接口"])
        async def qry_trades(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                strategyid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询策略成交接口
            
            获取指定策略的所有成交记录。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），策略所属的组合标识符
            @param strategyid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、trades（成交列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将策略ID赋值给sid变量
            sid = strategyid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取策略成交列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "trades": self.__data_mgr__.get_trades(gid, sid)  # 成交列表
                }

            # 返回响应结果
            return ret

        # 查询策略信号
        @app.post("/mgr/qrysigs", tags=["策略管理接口"])
        async def qry_signals(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                strategyid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询策略信号接口
            
            获取指定策略的所有交易信号记录。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），策略所属的组合标识符
            @param strategyid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、signals（信号列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将策略ID赋值给sid变量
            sid = strategyid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取策略信号列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "signals": self.__data_mgr__.get_signals(gid, sid)  # 信号列表
                }

            # 返回响应结果
            return ret

        # 查询策略回合
        @app.post("/mgr/qryrnds", tags=["策略管理接口"])
        async def qry_rounds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                strategyid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询策略回合接口
            
            获取指定策略的所有交易回合记录。回合是指一次完整的开仓到平仓过程。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），策略所属的组合标识符
            @param strategyid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、rounds（回合列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将策略ID赋值给sid变量
            sid = strategyid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取策略回合列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "rounds": self.__data_mgr__.get_rounds(gid, sid)  # 回合列表
                }

            # 返回响应结果
            return ret

        # 查询策略持仓
        @app.post("/mgr/qrypos", tags=["策略管理接口"])
        async def qry_positions(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                strategyid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询策略持仓接口
            
            获取指定策略的当前持仓信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），策略所属的组合标识符
            @param strategyid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、positions（持仓列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将策略ID赋值给sid变量
            sid = strategyid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取策略持仓列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "positions": self.__data_mgr__.get_positions(gid, sid)  # 持仓列表
                }

            # 返回响应结果
            return ret

        # 查询策略绩效
        @app.post("/mgr/qryfunds", tags=["策略管理接口"])
        async def qry_funds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                strategyid: str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询策略资金曲线接口
            
            获取指定策略的资金曲线数据，用于分析策略的绩效表现。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），策略所属的组合标识符
            @param strategyid: 策略ID（必填），要查询的策略标识符
            @return: 包含result（结果码）、message（消息）、funds（资金曲线数据）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将策略ID赋值给sid变量
            sid = strategyid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取策略资金曲线数据
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "funds": self.__data_mgr__.get_funds(gid, sid)  # 资金曲线数据
                }

            # 返回响应结果
            return ret

        # 查询通道订单
        @app.post("/mgr/qrychnlords", tags=["交易通道管理接口"])
        async def qry_channel_orders(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                channelid: str = Body(..., title="通道ID", embed=True)
        ):
            """
            查询通道订单接口
            
            获取指定交易通道的所有订单记录。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），通道所属的组合标识符
            @param channelid: 通道ID（必填），要查询的交易通道标识符
            @return: 包含result（结果码）、message（消息）、orders（订单列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将通道ID赋值给cid变量
            cid = channelid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取通道订单列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "orders": self.__data_mgr__.get_channel_orders(gid, cid)  # 订单列表
                }

            # 返回响应结果
            return ret

        # 查询通道成交
        @app.post("/mgr/qrychnltrds", tags=["交易通道管理接口"])
        async def qry_channel_trades(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                channelid: str = Body(..., title="通道ID", embed=True)
        ):
            """
            查询通道成交接口
            
            获取指定交易通道的所有成交记录。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），通道所属的组合标识符
            @param channelid: 通道ID（必填），要查询的交易通道标识符
            @return: 包含result（结果码）、message（消息）、trades（成交列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将通道ID赋值给cid变量
            cid = channelid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取通道成交列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "trades": self.__data_mgr__.get_channel_trades(gid, cid)  # 成交列表
                }

            # 返回响应结果
            return ret

        # 查询通道持仓
        @app.post("/mgr/qrychnlpos", tags=["交易通道管理接口"])
        async def qry_channel_position(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                channelid: str = Body(..., title="通道ID", embed=True)
        ):
            """
            查询通道持仓接口
            
            获取指定交易通道的当前持仓信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），通道所属的组合标识符
            @param channelid: 通道ID（必填），要查询的交易通道标识符
            @return: 包含result（结果码）、message（消息）、positions（持仓列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将通道ID赋值给cid变量
            cid = channelid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取通道持仓列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "positions": self.__data_mgr__.get_channel_positions(gid, cid)  # 持仓列表
                }

            # 返回响应结果
            return ret

        # 查询通道资金
        @app.post("/mgr/qrychnlfund", tags=["交易通道管理接口"])
        async def qry_channel_funds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                channelid: str = Body(..., title="通道ID", embed=True)
        ):
            """
            查询通道资金接口
            
            获取指定交易通道的资金信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），通道所属的组合标识符
            @param channelid: 通道ID（必填），要查询的交易通道标识符
            @return: 包含result（结果码）、message（消息）、funds（资金信息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid
            # 将通道ID赋值给cid变量
            cid = channelid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取通道资金信息
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "funds": self.__data_mgr__.get_channel_funds(gid, cid)  # 资金信息
                }

            # 返回响应结果
            return ret

        # 查询用户列表
        @app.post("/mgr/qryusers", tags=["系统管理接口"])
        @app.get("/mgr/qryusers", tags=["系统管理接口"])
        async def qry_users(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询用户列表接口
            
            获取系统中所有用户的列表。支持GET和POST两种请求方式。
            返回的用户信息中不包含密码字段，确保安全性。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、users（用户列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 从数据管理器获取所有用户列表
            users = self.__data_mgr__.get_users()
            # 遍历所有用户，移除密码字段，确保安全性
            for usrInfo in users:
                usrInfo.pop("passwd")

            # 构建成功响应，包含用户列表（不包含密码）
            ret = {
                "result": 0,  # 成功码
                "message": "",
                "users": users  # 用户列表
            }

            # 返回响应结果
            return ret

        # 提交用户信息
        @app.post("/mgr/cmtuser", tags=["系统管理接口"])
        async def cmd_commit_user(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                loginid: str = Body(..., title="登录名", embed=True),
                name: str = Body(..., title="用户姓名", embed=True),
                passwd: str = Body("", title="登录密码", embed=True),
                role: str = Body("", title="用户角色", embed=True),
                iplist: str = Body("", title="限定ip", embed=True),
                products: list = Body([], title="产品列表", embed=True),
                remark: str = Body("", title="备注信息", embed=True)
        ):
            """
            提交用户信息接口
            
            添加或更新用户信息。如果用户不存在则创建新用户，如果存在则更新用户信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param loginid: 登录名（必填），用户的登录标识符
            @param name: 用户姓名（必填），用户的显示名称
            @param passwd: 登录密码（可选，默认空字符串），如果为空则不更新密码
            @param role: 用户角色（可选，默认空字符串），如"admin"、"user"等
            @param iplist: 限定IP（可选，默认空字符串），限制用户登录的IP地址列表
            @param products: 产品列表（可选，默认空列表），用户可访问的产品ID列表
            @param remark: 备注信息（可选，默认空字符串），用户的备注说明
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 构建用户信息字典
            userinfo = {
                "loginid": loginid,  # 登录名
                "name": name,  # 用户姓名
                "passwd": passwd,  # 登录密码（明文，数据管理器会加密）
                "role": role,  # 用户角色
                "iplist": iplist,  # 限定IP列表
                "products": ",".join(products),  # 产品列表（转换为逗号分隔的字符串）
                "remark": remark  # 备注信息
            }

            # 调用数据管理器添加或更新用户，传入用户信息和操作者
            self.__data_mgr__.add_user(userinfo, adminInfo["loginid"])
            # 构建成功响应
            ret = {
                "result": 0,  # 成功码
                "message": "Ok"
            }

            # 记录提交用户信息的操作日志
            self.__data_mgr__.log_action(adminInfo, "cmtuser", json.dumps(userinfo))

            # 返回响应结果
            return ret

        # 删除用户
        @app.post("/mgr/deluser", tags=["系统管理接口"])
        async def cmd_delete_user(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                loginid: str = Body(..., title="用户名", embed=True)
        ):
            """
            删除用户接口
            
            删除指定的用户账户及其相关信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param loginid: 用户名（必填），要删除的用户登录名
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 调用数据管理器删除用户，如果删除成功则记录操作日志
            if self.__data_mgr__.del_user(loginid, adminInfo["loginid"]):
                # 记录删除用户的操作日志
                self.__data_mgr__.log_action(adminInfo, "delusr", loginid)
            # 构建成功响应（无论删除是否成功都返回成功，因为用户可能不存在）
            ret = {
                "result": 0,  # 成功码
                "message": "Ok"
            }

            # 返回响应结果
            return ret

        # 修改密码
        @app.post("/mgr/resetpwd", tags=["系统管理接口"])
        async def reset_pwd(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                loginid: str = Body(..., title="用户名", embed=True),
                passwd: str = Body(..., title="新密码", embed=True)
        ):
            """
            重置用户密码接口
            
            管理员重置指定用户的登录密码。需要管理员权限。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param loginid: 用户名（必填），要重置密码的用户登录名
            @param passwd: 新密码（必填），要设置的新密码
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将登录名赋值给user变量
            user = loginid
            # 将新密码赋值给pwd变量
            pwd = passwd

            # 检查用户名和新密码是否为空
            if len(pwd) == 0 or len(user) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -1,  # 错误码：参数错误
                    "message": "密码都不能为空"
                }
            else:
                # 使用MD5加密新密码：将用户名和新密码拼接后计算MD5哈希值
                encpwd = hashlib.md5((user + pwd).encode("utf-8")).hexdigest()
                # 从数据管理器获取用户信息
                usrInf = self.__data_mgr__.get_user(user)
                # 检查用户是否存在
                if usrInf is None:
                    # 构建用户不存在的错误响应
                    ret = {
                        "result": -1,  # 错误码：用户不存在
                        "message": "用户不存在"
                    }
                else:
                    # 修改用户密码，传入用户名、加密后的新密码和操作者
                    self.__data_mgr__.mod_user_pwd(user, encpwd, adminInfo["loginid"])
                    # 记录重置密码的操作日志
                    self.__data_mgr__.log_action(adminInfo, "resetpwd", loginid)
                    # 构建成功响应
                    ret = {
                        "result": 0,  # 成功码
                        "message": "Ok"
                    }

            # 返回响应结果
            return ret

        # 查询操作记录
        @app.post("/mgr/qryacts", tags=["系统管理接口"])
        async def qry_actions(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                sdate: int = Body(..., title="开始日期", embed=True),
                edate: int = Body(..., title="结束日期", embed=True)
        ):
            """
            查询操作记录接口
            
            获取指定日期范围内的系统操作记录，用于审计和追踪。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param sdate: 开始日期（必填），格式为YYYYMMDD的整数，如20230101
            @param edate: 结束日期（必填），格式为YYYYMMDD的整数，如20231231
            @return: 包含result（结果码）、message（消息）、actions（操作记录列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 构建成功响应，调用数据管理器获取操作记录列表
            ret = {
                "result": 0,  # 成功码
                "message": "",
                "actions": self.__data_mgr__.get_actions(sdate, edate)  # 操作记录列表
            }

            # 返回响应结果
            return ret

        # 查询全部调度
        @app.post("/mgr/qrymons", tags=["调度器管理接口"])
        @app.get("/mgr/qrymons", tags=["调度器管理接口"])
        async def qry_mon_apps(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询全部调度任务接口
            
            获取看门狗服务中所有调度任务的列表。支持GET和POST两种请求方式。
            每个调度任务会标记是否为策略组合。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、schedules（调度任务列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 从看门狗服务获取所有调度任务
            schedules = self._dog.get_apps()
            # 遍历所有调度任务，标记是否为策略组合
            for appid in schedules:
                schedules[appid]["group"] = self.__data_mgr__.has_group(appid)

            # 构建成功响应，包含调度任务列表
            ret = {
                "result": 0,  # 成功码
                "message": "",
                "schedules": schedules  # 调度任务列表（包含是否为组合的标记）
            }

            # 返回响应结果
            return ret

        @app.post("/mgr/startapp", tags=["调度器管理接口"])
        async def cmd_start_app(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                appid: str = Body(..., title="AppID", embed=True)
        ):
            """
            启动调度任务接口
            
            启动指定的调度任务。如果任务未运行，则启动它；如果已经运行，则直接返回成功。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param appid: AppID（必填），要启动的调度任务标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 检查调度任务是否存在
            if not self._dog.has_app(appid):
                # 构建任务不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：任务不存在
                    "message": "App不存在"
                }
            else:
                # 如果任务未运行，调用看门狗服务启动它
                if not self._dog.isRunning(appid):
                    self._dog.start(appid)
                # 构建成功响应
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok"
                }
                # 记录启动任务的操作日志
                self.__data_mgr__.log_action(adminInfo, "startapp", appid)

            # 返回响应结果
            return ret

        # 组合停止
        @app.post("/mgr/stopapp", tags=["调度器管理接口"])
        async def cmd_stop_app(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                appid: str = Body(..., title="AppID", embed=True)
        ):
            """
            停止调度任务接口
            
            停止指定的调度任务。如果任务正在运行，则停止它；如果已经停止，则直接返回成功。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param appid: AppID（必填），要停止的调度任务标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 检查调度任务是否存在
            if not self._dog.has_app(appid):
                # 构建任务不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：任务不存在
                    "message": "App不存在"
                }
            else:
                # 如果任务正在运行，调用看门狗服务停止它
                if self._dog.isRunning(appid):
                    self._dog.stop(appid)
                # 构建成功响应
                ret = {
                    "result": 0,  # 成功码
                    "message": "Ok"
                }

                # 记录停止任务的操作日志
                self.__data_mgr__.log_action(adminInfo, "stopapp", appid)

            # 返回响应结果
            return ret

        # 查询调度日志
        @app.post("/mgr/qrymonlog", tags=["调度器管理接口"])
        @app.get("/mgr/qrymonlog", tags=["调度器管理接口"])
        async def qry_mon_logs(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            查询调度日志接口
            
            获取监控服务器的日志内容。读取WtMonSvr.log文件的最后100行。
            支持GET和POST两种请求方式。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、content（日志内容）、lines（行数）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 构建日志文件路径（当前工作目录下的logs文件夹）
            filename = os.getcwd() + "/logs/WtMonSvr.log"
            # 读取日志文件的最后100行，使用UTF-8编码
            content, lines = get_tail(filename, 100, "UTF-8")
            # 构建成功响应，包含日志内容和行数
            ret = {
                "result": 0,  # 成功码
                "message": "Ok",
                "content": content,  # 日志内容（最后100行）
                "lines": lines  # 实际读取的行数
            }

            # 返回响应结果
            return ret

        # 删除调度任务
        @app.post("/mgr/delapp", tags=["调度器管理接口"])
        async def cmd_del_app(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                appid: str = Body(..., title="AppID", embed=True)
        ):
            """
            删除调度任务接口
            
            删除指定的调度任务。删除前需要先停止任务。
            如果任务是策略组合，则不能通过此接口删除，需要从组合管理删除。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param appid: AppID（必填），要删除的调度任务标识符
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, adminInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return adminInfo

            # 将AppID赋值给id变量
            id = appid

            # 检查AppID是否为空
            if len(id) == 0:
                # 构建参数为空的错误响应
                ret = {
                    "result": -1,  # 错误码：参数错误
                    "message": "组合ID不能为空"
                }
            # 检查是否为策略组合，如果是则不能通过此接口删除
            elif self.__data_mgr__.has_group(id):
                # 构建是策略组合的错误响应
                ret = {
                    "result": -2,  # 错误码：是策略组合
                    "message": "该调度任务是策略组合，请从组合管理删除"
                }
            # 检查调度任务是否存在
            elif not self._dog.has_app(id):
                # 构建任务不存在的错误响应
                ret = {
                    "result": -3,  # 错误码：任务不存在
                    "message": "该调度任务不存在"
                }
            # 检查任务是否正在运行，如果正在运行则不能删除
            elif self._dog.isRunning(id):
                # 构建任务正在运行的错误响应
                ret = {
                    "result": -4,  # 错误码：任务正在运行
                    "message": "请先停止该任务"
                }
            else:
                if True:
                    # 从看门狗服务中删除调度任务
                    self._dog.delApp(id)
                    # 构建成功响应
                    ret = {
                        "result": 0,  # 成功码
                        "message": "Ok"
                    }

                    # 记录删除任务的操作日志
                    self.__data_mgr__.log_action(adminInfo, "delapp", id)
                else:
                    # 如果请求处理出现异常（此分支通常不会执行）
                    ret = {
                        "result": -1,  # 错误码：处理异常
                        "message": "请求解析失败"
                    }

            # 返回响应结果
            return ret

        # 查询组合持仓
        @app.post("/mgr/qryportpos", tags=["组合盘管理接口"])
        async def qry_group_positions(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合持仓接口
            
            获取指定组合的所有策略的汇总持仓信息。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、positions（持仓列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取组合持仓列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "positions": self.__data_mgr__.get_group_positions(gid)  # 组合持仓列表
                }

            # 返回响应结果
            return ret

        # 查询组合成交
        @app.post("/mgr/qryporttrd", tags=["组合盘管理接口"])
        async def qry_group_trades(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合成交接口
            
            获取指定组合的所有策略的汇总成交记录。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、trades（成交列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取组合成交列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "trades": self.__data_mgr__.get_group_trades(gid)  # 组合成交列表
                }

            # 返回响应结果
            return ret

        # 查询组合回合
        @app.post("/mgr/qryportrnd", tags=["组合盘管理接口"])
        async def qry_group_rounds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合回合接口
            
            获取指定组合的所有策略的汇总交易回合记录。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、rounds（回合列表）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取组合回合列表
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "rounds": self.__data_mgr__.get_group_rounds(gid)  # 组合回合列表
                }

            # 返回响应结果
            return ret

        # 查询组合资金
        @app.post("/mgr/qryportfunds", tags=["组合盘管理接口"])
        async def qry_group_funds(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合资金接口
            
            获取指定组合的所有策略的汇总资金曲线数据。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、funds（资金曲线数据）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取组合资金曲线数据
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "funds": self.__data_mgr__.get_group_funds(gid)  # 组合资金曲线数据
                }

            # 返回响应结果
            return ret

        # 查询组合绩效分析
        @app.post("/mgr/qryportperfs", tags=["组合盘管理接口"])
        async def qry_group_perfs(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合绩效分析接口
            
            获取指定组合的绩效分析数据，包括收益率、夏普比率、最大回撤等指标。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、performance（绩效分析数据）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取组合绩效分析数据
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "performance": self.__data_mgr__.get_group_performances(gid)  # 绩效分析数据
                }

            # 返回响应结果
            return ret

        # 查询组合过滤器
        @app.post("/mgr/qryportfilters", tags=["组合盘管理接口"])
        async def qry_group_filters(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True)
        ):
            """
            查询组合过滤器接口
            
            获取指定组合的过滤器配置，用于前端数据展示时的过滤。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要查询的组合标识符
            @return: 包含result（结果码）、message（消息）、filters（过滤器配置）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给gid变量
            gid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(gid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                # 构建成功响应，调用数据管理器获取组合过滤器配置
                ret = {
                    "result": 0,  # 成功码
                    "message": "",
                    "filters": self.__data_mgr__.get_group_filters(gid)  # 过滤器配置
                }

            # 返回响应结果
            return ret

        # 提交组合过滤器
        @app.post("/mgr/cmtgrpfilters", tags=["组合盘管理接口"])
        async def cmd_commit_group_filters(
                request: Request,
                token: str = Body(None, title="访问令牌", embed=True),
                groupid: str = Body(..., title="组合ID", embed=True),
                filters: dict = Body(..., title="过滤器", embed=True)
        ):
            """
            提交组合过滤器接口
            
            保存或更新指定组合的过滤器配置。过滤器用于控制前端数据展示时的过滤规则。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @param groupid: 组合ID（必填），要保存过滤器的组合标识符
            @param filters: 过滤器（必填），包含策略过滤器、合约过滤器、执行器过滤器等的字典
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, usrInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return usrInfo

            # 将组合ID赋值给grpid变量
            grpid = groupid

            # 检查组合是否存在
            if not self.__data_mgr__.has_group(grpid):
                # 构建组合不存在的错误响应
                ret = {
                    "result": -1,  # 错误码：组合不存在
                    "message": "组合不存在"
                }
            else:
                try:
                    # 调用数据管理器保存组合过滤器配置
                    self.__data_mgr__.set_group_filters(grpid, filters)
                    # 构建成功响应
                    ret = {
                        "result": 0,  # 成功码
                        "message": "Ok"
                    }
                except:
                    # 捕获所有异常，构建过滤器保存失败的错误响应
                    ret = {
                        "result": -1,  # 错误码：保存失败
                        "message": "过滤器保存失败"
                    }

            # 返回响应结果
            return ret
        
        @app.get("/mgr/auth", tags=["令牌认证"])
        @app.post("/mgr/auth")
        async def authority(
            request: Request,
            token: str = Body(None, title="访问令牌", embed=True)
        ):
            """
            令牌认证接口
            
            验证访问令牌的有效性并返回用户信息。支持GET和POST两种请求方式。
            用于客户端验证token是否仍然有效。
            
            @param request: FastAPI请求对象
            @param token: 访问令牌（可选），如果提供则使用token认证，否则使用session认证
            @return: 包含result（结果码）、message（消息）、userinfo（用户信息）的字典
            """
            # 检查用户认证状态，返回认证结果和用户信息
            bSucc, userInfo = check_auth(request, token, self.__sec_key__)
            # 如果认证失败，直接返回错误信息
            if not bSucc:
                return userInfo
            else:
                # 构建成功响应，包含用户信息
                return {
                    "result": 0,  # 成功码
                    "message": "Ok",
                    "userinfo": userInfo  # 用户信息（不包含密码）
                }

    def init_comm_apis(self, app: FastAPI):
        """
        初始化通用API路由
        
        该方法注册通用的HTTP API接口，包括：
        - 控制台入口：重定向到控制台首页
        - 移动端入口：重定向到移动端首页
        - 网站图标：返回favicon.ico文件
        - 回测支持检查：检查是否支持在线回测功能
        
        这些接口通常不需要认证，用于提供基本的Web访问入口和功能检查。
        
        @param app: FastAPI应用实例，用于注册路由
        """
        @app.get("/console")
        async def console_entry():
            """
            控制台入口接口
            
            重定向到控制台首页，用于访问Web管理界面。
            
            @return: 重定向响应，指向/console/index.html
            """
            # 返回重定向响应，指向控制台首页
            return RedirectResponse("/console/index.html")
        
        @app.get("/mobile")
        async def mobile_entry():
            """
            移动端入口接口
            
            重定向到移动端首页，用于移动设备访问。
            
            @return: 重定向响应，指向/mobile/index.html
            """
            # 返回重定向响应，指向移动端首页
            return RedirectResponse("/mobile/index.html")

        @app.get("/favicon.ico")
        async def favicon_entry():
            """
            网站图标接口
            
            返回网站的favicon图标文件。
            
            @return: 文件响应，包含favicon.ico文件
            """
            # 返回favicon.ico文件的文件响应
            return FileResponse(os.path.join(self.static_folder, "favicon.ico"))
        
        @app.get("/hasbt")
        @app.post("/hasbt")
        async def check_btmon():
            """
            检查回测支持接口
            
            检查当前服务器是否支持在线回测功能。
            支持GET和POST两种请求方式。
            
            @return: 包含result（结果码）、message（消息）的字典
            """
            # 检查回测管理器是否已配置
            if self.__bt_mon__ is None:
                # 构建不支持回测的响应
                return {
                    "result": -1,  # 错误码：不支持回测
                    "message": "不支持在线回测"
                }
            else:
                # 构建支持回测的响应
                return {
                    "result": 0,  # 成功码
                    "message": "Ok"
                }

    def __run_impl__(self, port: int, host: str):
        """
        服务器运行实现方法（私有方法）
        
        启动看门狗服务、推送服务器和Web服务器。
        
        @param port: 端口号（整数），服务器监听的端口
        @param host: 主机地址（字符串），服务器绑定的主机地址
        """
        # 启动看门狗服务，开始监控应用
        self._dog.run()
        # 启动推送服务器，开始WebSocket推送服务
        self.push_svr.run()
        # 使用uvicorn运行FastAPI应用
        uvicorn.run(self.app, port=port, host=host)

    def run(self, port: int = 8080, host="0.0.0.0", bSync: bool = True):
        """
        启动监控服务器
        
        启动监控服务器，可以同步运行（阻塞）或异步运行（后台线程）。
        在Linux系统中，会忽略子进程结束信号，避免僵尸进程。
        
        @param port: 端口号（整数，默认8080），服务器监听的端口
        @param host: 主机地址（字符串，默认"0.0.0.0"），"0.0.0.0"表示监听所有网络接口
        @param bSync: 是否同步运行（布尔值，默认True），True表示阻塞运行，False表示后台线程运行
        """
        # 仅linux生效，在linux中，子进程会一直等待父进程处理其结束信号才能释放，如果不加这一句忽略子进程的结束信号，子进程就无法结束
        if not isWindows():
            # 忽略子进程结束信号，避免僵尸进程
            signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        # 根据bSync参数决定运行方式
        if bSync:
            # 同步运行（阻塞）
            self.__run_impl__(port, host)
        else:
            # 异步运行（后台线程）
            import threading
            self.worker = threading.Thread(target=self.__run_impl__, args=(port, host,))
            self.worker.setDaemon(True)  # 设置为守护线程
            self.worker.start()

    def init_logging(self):
        """
        初始化日志系统
        
        初始化日志系统配置。当前实现为空，可以根据需要添加日志初始化逻辑。
        """
        pass

    def on_start(self, grpid: str):
        """
        应用启动事件回调函数（实现WatcherSink接口）
        
        当看门狗服务检测到应用启动时，会调用此函数。
        向客户端推送应用启动事件。
        
        @param grpid: 组合ID（字符串），启动的应用所属的组合标识
        """
        # 检查组合是否存在
        if self.__data_mgr__.has_group(grpid):
            # 通过推送服务器向该组合的所有客户端推送启动事件
            self.push_svr.notifyGrpEvt(grpid, 'start')

    def on_stop(self, grpid: str, isErr: bool):
        """
        应用停止事件回调函数（实现WatcherSink接口）
        
        当看门狗服务检测到应用停止时，会调用此函数。
        向客户端推送应用停止事件，如果是异常停止则通知管理员。
        
        @param grpid: 组合ID（字符串），停止的应用所属的组合标识
        @param isErr: 是否因错误停止（布尔值），True表示异常停止，False表示正常停止
        """
        # 检查组合是否存在
        if self.__data_mgr__.has_group(grpid):
            # 通过推送服务器向该组合的所有客户端推送停止事件
            self.push_svr.notifyGrpEvt(grpid, 'stop')

        # 如果是错误停止且配置了事件回调接口，需要通知管理员
        if isErr and self._sink_:
            # 从数据管理器获取组合信息
            grpInfo = self.__data_mgr__.get_group(grpid)
            # 通过事件回调接口通知管理员，使用致命错误级别，包含组合名称和ID
            self._sink_.notify("fatal", "检测到 %s[%s] 意外停止, 请及时处理!!!" % (grpInfo["name"], grpid))

    def on_output(self, grpid: str, tag: str, time: int, message: str):
        """
        应用输出事件回调函数（实现WatcherSink接口）
        
        当应用产生日志输出时，会调用此函数。
        向客户端推送日志消息。
        
        @param grpid: 组合ID（字符串），产生日志的应用所属的组合标识
        @param tag: 日志标签（字符串），用于标识日志来源
        @param time: 日志时间戳（整数），日志产生的时间
        @param message: 日志消息内容（字符串）
        """
        # 检查组合是否存在
        if self.__data_mgr__.has_group(grpid):
            # 通过推送服务器向该组合的所有客户端推送日志消息，包含标签、时间戳和消息内容
            self.push_svr.notifyGrpLog(grpid, tag, time, message)

    def on_order(self, grpid: str, chnl: str, ordInfo: dict):
        """
        订单事件回调函数（实现WatcherSink接口）
        
        当应用产生订单事件时，会调用此函数。
        向客户端推送订单事件。
        
        @param grpid: 组合ID（字符串），产生订单的应用所属的组合标识
        @param chnl: 交易通道名称（字符串），订单来源的交易接口
        @param ordInfo: 订单信息字典，包含订单的详细信息（如订单号、合约、方向、价格、数量等）
        """
        # 通过推送服务器向该组合和通道的所有客户端推送订单事件，事件类型为'order'
        self.push_svr.notifyGrpChnlEvt(grpid, chnl, 'order', ordInfo)

    def on_trade(self, grpid: str, chnl: str, trdInfo: dict):
        """
        成交事件回调函数（实现WatcherSink接口）
        
        当应用产生成交事件时，会调用此函数。
        向客户端推送成交事件。
        
        @param grpid: 组合ID（字符串），产生成交的应用所属的组合标识
        @param chnl: 交易通道名称（字符串），成交来源的交易接口
        @param trdInfo: 成交信息字典，包含成交的详细信息（如成交号、合约、方向、价格、数量、时间等）
        """
        # 通过推送服务器向该组合和通道的所有客户端推送成交事件，事件类型为'trade'
        self.push_svr.notifyGrpChnlEvt(grpid, chnl, 'trade', trdInfo)

    def on_notify(self, grpid: str, chnl: str, message: str):
        """
        通知事件回调函数（实现WatcherSink接口）
        
        当应用产生通知事件时，会调用此函数。
        向客户端推送通知消息。
        
        @param grpid: 组合ID（字符串），产生通知的应用所属的组合标识
        @param chnl: 交易通道名称（字符串），通知来源的交易接口
        @param message: 通知消息内容（字符串），通知的具体内容
        """
        # 通过推送服务器向该组合和通道的所有客户端推送通知事件，事件类型为'notify'
        self.push_svr.notifyGrpChnlEvt(grpid, chnl, 'notify', message)

    def on_timeout(self, grpid: str):
        """
        消息超时事件回调函数（实现WatcherSink接口）
        
        当应用的消息接收超时时，会调用此函数。
        如果启用了超时通知，则通知管理员。
        
        @param grpid: 组合ID（字符串），消息超时的应用所属的组合标识
        """
        # 检查是否启用了超时通知，如果未启用则直接返回，不进行任何处理
        if not self.notifyTimeout:
            return
            
        # 检查是否配置了事件回调接口
        if self._sink_:
            # 从数据管理器获取组合信息，用于构建通知消息
            grpInfo = self.__data_mgr__.get_group(grpid)
            # 通过事件回调接口通知管理员，使用致命错误级别（fatal），包含组合名称和ID
            self._sink_.notify("fatal", f'检测到 {grpInfo["name"]}[{grpid}]的MQ消息超时，请及时检查并处理!!!')
