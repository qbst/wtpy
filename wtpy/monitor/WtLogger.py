"""
WonderTrader日志记录器模块

该模块提供了一个统一的日志记录接口，封装了Python标准库的logging模块。
支持同时将日志输出到文件和控制台，使用UTF-8编码确保中文日志的正确显示。

设计目的：
1. 提供统一的日志记录接口，简化日志使用
2. 自动创建日志目录，确保日志文件能够正常写入
3. 同时支持文件和控制台输出，方便调试和查看
4. 使用UTF-8编码，确保中文日志的正确显示
"""

import logging
import os

class WtLogger:
    """
    WonderTrader日志记录器类
    
    封装了Python标准库的logging模块，提供统一的日志记录接口。
    支持同时将日志输出到文件和控制台，使用UTF-8编码确保中文日志的正确显示。
    
    使用示例：
        logger = WtLogger("MyApp", "app.log")
        logger.info("这是一条信息日志")
        logger.warn("这是一条警告日志")
        logger.error("这是一条错误日志")
    """

    def __init__(self, catName:str='', filename:str="out.log"):
        """
        初始化日志记录器
        
        创建日志记录器实例，配置日志输出到文件和控制台。
        如果日志目录不存在，会自动创建。
        
        @param catName: 日志分类名称（字符串，默认空字符串），用于标识日志来源
        @param filename: 日志文件名（字符串，默认"out.log"），日志文件将保存在logs目录下
        """
        # 创建日志记录器实例，使用分类名称作为logger名称
        self.logger = logging.getLogger(catName)
        # 设置日志级别为DEBUG，确保所有级别的日志都能被记录
        self.logger.setLevel(logging.DEBUG)

        # ========== 创建文件日志处理器 ==========
        # 构建日志文件输出路径，注意logs是个文件夹，一定要加上/，不然会导致输出路径错误，把logs变成文件名的一部分了
        log_path = os.getcwd()+"/logs/"
        # 如果日志目录不存在，创建日志目录
        if not os.path.exists(log_path):
            os.mkdir(log_path)
        # 构建完整的日志文件路径
        logname = log_path + filename
        # 创建文件日志处理器，指定utf-8格式编码，避免输出的日志文本乱码，使用追加模式（'a'）写入
        fh = logging.FileHandler(logname,encoding = 'utf-8',mode='a')
        # 设置文件日志级别为INFO，只记录INFO及以上级别的日志
        fh.setLevel(logging.INFO)

        # ========== 创建控制台日志处理器 ==========
        # 创建控制台日志处理器，用于将日志输出到标准输出（控制台）
        ch = logging.StreamHandler()
        # 设置控制台日志级别为INFO，只输出INFO及以上级别的日志
        ch.setLevel(logging.INFO)

        # ========== 配置日志格式 ==========
        # 定义日志输出格式：[时间 - 级别] 消息内容，时间格式为年-月-日 时:分:秒
        formatter = logging.Formatter('[%(asctime)s - %(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        # 为文件处理器设置格式
        fh.setFormatter(formatter)
        # 为控制台处理器设置格式
        ch.setFormatter(formatter)

        # ========== 注册日志处理器 ==========
        # 将文件日志处理器添加到logger
        self.logger.addHandler(fh)
        # 将控制台日志处理器添加到logger
        self.logger.addHandler(ch)

    def info(self, message:str):
        """
        记录信息级别日志
        
        记录一般的信息性日志，用于记录程序的正常运行状态。
        
        @param message: 日志消息内容（字符串）
        """
        # 调用logger的info方法记录信息级别日志
        self.logger.info(message)

    def warn(self, message:str):
        """
        记录警告级别日志
        
        记录警告性日志，用于记录可能存在问题但不影响程序运行的情况。
        
        @param message: 日志消息内容（字符串）
        """
        # 调用logger的warn方法记录警告级别日志
        self.logger.warn(message)

    def error(self, message:str):
        """
        记录错误级别日志
        
        记录错误性日志，用于记录程序运行中的错误情况。
        
        @param message: 日志消息内容（字符串）
        """
        # 调用logger的error方法记录错误级别日志
        self.logger.error(message)

    def fatal(self, message:str):
        """
        记录致命错误级别日志
        
        记录致命错误日志，用于记录导致程序无法继续运行的严重错误。
        
        @param message: 日志消息内容（字符串）
        """
        # 调用logger的fatal方法记录致命错误级别日志
        self.logger.fatal(message)
