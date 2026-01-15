"""
扩展工具定义模块

本模块定义了扩展工具的基础类，用于扩展框架的功能。
主要包括指标输出工具和数据报告器两类扩展工具。

主要功能：
1. BaseIndexWriter：指标输出工具基类，用于将策略计算的指标数据输出到外部
2. BaseDataReporter：数据报告器基类，用于将策略的运行数据报告到外部系统
"""

# 导入JSON处理模块
import json
# 导入时间处理模块
import time
# 导入线程模块
from threading import Thread

def fileToJson(filename, encoding="utf-8"):
    """
    将文件内容读取并解析为JSON对象
    
    辅助函数，用于读取JSON格式的文件并解析为Python字典对象。
    
    @filename: 文件路径
    @encoding: 文件编码，默认为utf-8
    @return: 返回解析后的JSON对象（字典），如果解析失败则返回None
    """
    # 以只读模式打开文件
    f = open(filename, 'r')
    # 读取文件内容
    content = f.read()
    # 关闭文件
    f.close()
    try:
        # 尝试解析JSON内容
        return json.loads(content)
    except:
        # 解析失败返回None
        return None

class BaseIndexWriter:
    """
    基础指标输出工具类
    
    所有指标输出工具的基类，子类需要实现write_indicator方法来定义具体的输出逻辑。
    指标输出工具用于将策略计算的指标数据（如技术指标、自定义指标等）输出到外部存储
    或显示系统，便于分析和可视化。
    """

    def __init__(self):
        """
        构造函数
        
        初始化指标输出工具，基类中不做任何操作。
        """
        return

    def write_indicator(self, id:str, tag:str, time:int, data:dict):
        """
        写入指标数据（抽象方法）
        
        子类必须实现此方法，定义具体的指标数据输出逻辑。
        
        @id: 指标ID，用于标识不同的指标
        @tag: 数据标记，主要用于区分指标对应的周期，如m5、d等
        @time: 指标时间，格式如yyyymmddHHMM
        @data: 数据对象，一个字典，包含指标的各种数值
        @raise Exception: 基类中直接抛出异常，提示需要子类实现
        """
        # 基类中直接抛出异常，提示子类必须实现此方法
        raise Exception("Basic writer cannot output index data to any media")


class BaseDataReporter:
    """
    数据报告器基类
    
    所有数据报告器的基类，用于将策略的运行数据（如持仓、盈亏、资金等）报告到外部系统。
    支持实时数据报告、结算数据报告和初始化数据报告三种类型的报告。
    使用后台线程异步处理报告任务，避免阻塞主线程。
    """
    
    # 任务类型常量：报告实时数据
    TaskReportRTData        = 1
    # 任务类型常量：报告结算数据
    TaskReportSettleData    = 2
    # 任务类型常量：报告初始化数据
    TaskReportInitData      = 3

    def __init__(self, id:str):
        """
        构造函数
        
        初始化数据报告器，设置报告器ID。
        
        @id: 报告器ID，用于标识不同的报告器实例
        """
        # 初始化标志，表示报告器是否已初始化
        self.__inited__ = False
        # 报告器ID
        self.__id__ = id
        return

    def init(self):
        """
        初始化报告器
        
        读取策略标记文件，创建任务队列和后台线程。
        此方法需要在报告数据之前调用。
        """
        # 标记为已初始化
        self.__inited__ = True
        # 后台任务线程对象，初始为None
        self.__thrd_task__ = None
        # 任务队列，存储待处理的任务ID
        self.__tasks__ = list()
        # 停止标志，用于控制后台线程退出
        self.__stopped__ = False

        # 读取策略标记文件，获取策略名称列表
        filename = "./generated/marker.json"
        obj = fileToJson(filename)
        if obj is not None:
            # 保存策略名称列表
            self.stra_names = obj["marks"]

    def rpt_portfolio_rt_data_impl(self, rtData):
        """
        报告组合实时数据（抽象方法）
        
        子类必须实现此方法，定义组合实时数据的报告逻辑。
        
        @rtData: 组合实时数据字典，包含组合的资金、持仓等信息
        @raise Exception: 基类中直接抛出异常，提示需要子类实现
        """
        # 基类中直接抛出异常，提示子类必须实现此方法
        raise Exception("this method has not been implemented")

    def rpt_strategy_rt_data_impl(self, rtData):
        """
        报告策略实时数据（抽象方法）
        
        子类必须实现此方法，定义策略实时数据的报告逻辑。
        
        @rtData: 策略实时数据字典，包含策略的持仓、盈亏等信息
        @raise Exception: 基类中直接抛出异常，提示需要子类实现
        """
        # 基类中直接抛出异常，提示子类必须实现此方法
        raise Exception("this method has not been implemented")

    def rpt_init_data_impl(self, initData):
        """
        报告初始化数据（抽象方法）
        
        子类必须实现此方法，定义初始化数据的报告逻辑。
        
        @initData: 初始化数据字典，包含策略列表等信息
        @raise Exception: 基类中直接抛出异常，提示需要子类实现
        """
        # 基类中直接抛出异常，提示子类必须实现此方法
        raise Exception("this method has not been implemented")

    def __do_report_rt_data__(self):
        """
        执行实时数据报告（内部方法）
        
        读取组合数据和策略数据文件，调用子类实现的报告方法。
        """
        # 输出调试信息
        print("settle data reporter triggered")
        # 第一步，提交组合数据，读取portfolio数据文件
        filename = "./generated/portfolio/datas.json"
        objPort = fileToJson(filename)
        # 添加报告器ID到数据对象
        objPort["pid"] = self.__id__
        # 调用子类实现的组合数据报告方法
        self.rpt_portfolio_rt_data_impl(objPort)

        # 第二步，提交策略数据，遍历所有策略
        for sname in self.stra_names:
            # 读取策略数据文件
            filename = "./generated/stradata/" + sname + ".json"
            objStra = fileToJson(filename)
            # 添加报告器ID和策略ID到数据对象
            objStra["pid"] = self.__id__
            objStra["sid"] = sname

            # 调用子类实现的策略数据报告方法
            self.rpt_strategy_rt_data_impl(objStra)

    def __task_loop__(self):
        """
        任务循环（内部方法）
        
        后台线程的主循环，不断从任务队列中取出任务并执行。
        """
        # 循环处理任务，直到停止标志为True
        while not self.__stopped__:
            # 如果任务队列为空，则等待1秒后继续
            if len(self.__tasks__) == 0:
                time.sleep(1)
                continue
            else:
                # 从任务队列中取出第一个任务
                taskid = self.__tasks__.pop(0)
                # 根据任务类型执行相应的报告方法
                if taskid == self.TaskReportRTData:
                    # 执行实时数据报告
                    self.__do_report_rt_data__()
                elif taskid == self.TaskReportSettleData:
                    # 执行结算数据报告
                    self.__do_report_settle_data__()
                elif taskid == self.TaskReportInitData:
                    # 执行初始化数据报告
                    self.__do_report_init_data__()

    def __start__(self):
        """
        启动后台任务线程（内部方法）
        
        如果后台线程尚未启动，则创建并启动新线程。
        """
        # 如果后台线程未启动，则创建新线程
        if self.__thrd_task__ is None:
            # 创建后台线程，目标函数为任务循环
            self.__thrd_task__ = Thread(target=self.__task_loop__, name="reportthread")
            # 注释掉的代码：设置为守护线程（如果取消注释，主线程退出时子线程也会退出）
            # self.__thrd_task__.setDaemon(True)
            # 启动线程
            self.__thrd_task__.start()
            # 输出调试信息
            print("report thread started")

    def __do_report_init_data__(self):
        """
        执行初始化数据报告（内部方法）
        
        构造初始化数据对象，调用子类实现的报告方法。
        """
        # 创建初始化数据对象
        objInitData = dict()
        # 添加报告器ID
        objInitData["pid"] = self.__id__
        # 添加策略名称列表
        objInitData["strategies"] = self.stra_names
        # 调用子类实现的初始化数据报告方法
        self.rpt_init_data_impl(objInitData)

    def __do_report_settle_data__(self):
        """
        执行结算数据报告（内部方法）
        
        目前仅输出调试信息，具体实现由子类完成。
        """
        # 输出调试信息
        print("settle data reporter triggered")

    def report_rt_data(self):
        """
        报告实时数据
        
        将实时数据报告任务添加到任务队列，如果后台线程未启动则启动它。
        """
        # 输出调试信息
        print("rt data reporter triggered")
        # 将实时数据报告任务添加到任务队列
        self.__tasks__.append(self.TaskReportRTData)
        # 如果后台线程未启动，则启动它
        if self.__thrd_task__ is None:
            self.__start__()

    def report_settle_data(self):
        """
        报告结算数据
        
        将结算数据报告任务添加到任务队列，如果后台线程未启动则启动它。
        """
        # 将结算数据报告任务添加到任务队列
        self.__tasks__.append(self.TaskReportSettleData)
        # 如果后台线程未启动，则启动它
        if self.__thrd_task__ is None:
            self.__start__()

    def report_init_data(self):
        """
        报告初始化数据
        
        将初始化数据报告任务添加到任务队列，如果后台线程未启动则启动它。
        """
        # 将初始化数据报告任务添加到任务队列
        self.__tasks__.append(self.TaskReportInitData)
        # 如果后台线程未启动，则启动它
        if self.__thrd_task__ is None:
            self.__start__()
        
