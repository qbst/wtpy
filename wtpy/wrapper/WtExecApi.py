"""
执行器API包装模块

本模块提供WonderTrader独立执行器的Python接口封装。独立执行器用于执行目标仓位的设置，
可以根据策略信号自动调整仓位，实现策略与执行的分离。

主要功能：
1. 初始化执行器框架
2. 配置执行器参数
3. 设置目标仓位
4. 日志输出
5. 运行和释放执行器

使用单例模式确保全局只有一个执行器API实例。
"""

# 导入ctypes库，用于调用C++动态库
from ctypes import cdll, c_char_p, c_int, c_bool, c_double
# 导入平台辅助工具，用于获取动态库路径和编码转换
from .PlatformHelper import PlatformHelper as ph
# 导入单例装饰器，确保全局唯一实例
from wtpy.WtUtilDefs import singleton
# 导入操作系统模块
import os

@singleton
class WtExecApi:
    """
    WonderTrader独立执行器API包装类
    
    提供独立执行器功能的Python封装，用于根据策略信号自动执行仓位调整。
    使用单例模式，确保全局只有一个实例。
    """

    # api可以作为公共变量，存储C++动态库的接口
    api = None
    # 版本信息
    ver = "Unknown"

    def __init__(self):
        """
        初始化执行器API包装器
        """
        # 获取当前文件所在目录
        paths = os.path.split(__file__)
        # 获取执行器动态库文件名（包含平台和架构信息）
        dllname = ph.getModule("WtExecMon")
        # 拼接路径
        a = (paths[:-1] + (dllname,))
        # 生成完整的动态库路径
        _path = os.path.join(*a)
        # 加载C++动态库
        self.api = cdll.LoadLibrary(_path)

        # 设置get_version函数的返回类型：版本字符串（字符指针）
        self.api.get_version.restype = c_char_p
        # 获取并解码版本信息
        self.ver = bytes.decode(self.api.get_version())
        
        # 设置write_log函数的参数类型：日志级别（整数）、日志消息（字符串）、分类名称（字符串）
        self.api.write_log.argtypes = [c_int, c_char_p, c_char_p]
        # 设置config_exec函数的参数类型：配置文件（字符串）、是否为文件（布尔）
        self.api.config_exec.argtypes = [c_char_p, c_bool]
        # 设置init_exec函数的参数类型：日志配置（字符串）、是否为文件（布尔）
        self.api.init_exec.argtypes = [c_char_p, c_bool]
        # 设置set_position函数的参数类型：合约代码（字符串）、目标仓位（浮点数）
        self.api.set_position.argtypes = [c_char_p, c_double]

    def run(self):
        """
        运行执行器
        
        启动执行器主循环，开始监听和执行仓位调整指令。
        """
        # 调用C++库运行执行器
        self.api.run_exec()

    def release(self):
        """
        释放执行器资源
        
        停止执行器并释放相关资源。
        """
        # 调用C++库释放执行器
        self.api.release_exec()

    def write_log(self, level:int, message:str, catName:str = ""):
        """
        写入日志
        
        @param level: 日志级别（整数）
        @param message: 日志消息内容
        @param catName: 日志分类名称，默认为空字符串
        """
        # 调用C++库写入日志，Windows平台需要转换为GBK编码
        self.api.write_log(level, bytes(message, encoding = "utf8").decode('utf-8').encode('gbk'), bytes(catName, encoding = "utf8"))

    def config(self, cfgfile:str = 'cfgexec.yaml', isFile:bool = True):
        """
        配置执行器
        
        @param cfgfile: 配置文件路径或配置内容，默认为'cfgexec.yaml'
        @param isFile: 是否为文件路径，True表示文件路径，False表示配置内容，默认为True
        """
        # 调用C++库配置执行器
        self.api.config_exec(bytes(cfgfile, encoding = "utf8"), isFile)

    def initialize(self, logCfg:str = "logcfgexec.yaml", isFile:bool = True):
        """
        C接口初始化
        
        初始化执行器框架，加载日志配置。
        
        @param logCfg: 日志配置文件路径或配置内容，默认为"logcfgexec.yaml"
        @param isFile: 是否为文件路径，True表示文件路径，False表示配置内容，默认为True
        """
        # 调用C++库初始化执行器
        self.api.init_exec(bytes(logCfg, encoding = "utf8"), isFile)
        # 写入初始化成功日志
        self.write_log(102, "WonderTrader independent execution framework initialzied，version: %s" % (self.ver))

    def set_position(self, stdCode:str, target:float):
        """
        设置目标仓位
        
        设置指定合约的目标仓位，执行器会根据当前仓位自动调整。
        
        @param stdCode: 标准合约代码
        @param target: 目标仓位数量，正数表示多头，负数表示空头
        """
        # 调用C++库设置目标仓位
        self.api.set_position(bytes(stdCode, encoding = "utf8"), target)
