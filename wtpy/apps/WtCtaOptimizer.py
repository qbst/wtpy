"""
CTA策略参数优化模块

本模块用于对CTA（Commodity Trading Advisor，商品交易顾问）策略进行参数优化，
通过网格搜索的方式遍历参数空间，对每组参数进行回测，并分析回测结果，找出最优参数组合。

主要功能：
1. 支持可变参数和固定参数的设置
2. 自动生成参数组合并执行回测任务
3. 多进程并行执行回测，提高优化效率
4. 自动分析回测结果，生成绩效指标
5. 支持Python策略和C++策略的优化
6. 支持消息队列通知优化进度

设计逻辑：
- 使用多进程并行执行回测任务，充分利用多核CPU
- 将参数组合分组，每组共享一个回测引擎，减少IO开销
- 自动生成策略名称，包含参数信息，便于识别
- 回测完成后自动分析结果，生成summary.json文件
- 支持通过消息队列实时通知优化进度
"""

# 导入标准库模块
import multiprocessing  # 多进程支持
import time             # 时间相关操作
import json             # JSON数据处理
import yaml             # YAML配置文件解析
import datetime         # 日期时间处理
import ctypes           # C类型支持

# 导入第三方库
import os               # 操作系统接口
import math             # 数学函数
import pandas as pd     # 数据处理库
from pandas import DataFrame as df  # DataFrame类型别名

# 导入wtpy框架模块
from wtpy import WtBtEngine,EngineType  # 回测引擎和引擎类型
from wtpy.apps import WtBtAnalyst       # 回测分析器
from wtpy.apps.WtBtAnalyst import summary_analyze  # 概要分析函数
from wtpy.WtMsgQue import WtMsgQue,WtMQServer      # 消息队列

def fmtNAN(val, defVal = 0):
    """
    格式化NaN值
    
    如果值为NaN（Not a Number），则返回默认值，否则返回原值。
    用于处理数据分析中可能出现的NaN值。
    
    @param val: 待检查的值
    @param defVal: 默认值，当val为NaN时返回此值，默认为0
    @return: 格式化后的值
    """
    # 检查值是否为NaN
    if math.isnan(val):
        return defVal

    return val

# 创建消息队列对象
mq = WtMsgQue()

class OptimizeNotifier:
    """
    优化进度通知器类
    
    用于通过消息队列实时通知参数优化的进度，包括开始、停止和状态更新事件。
    支持外部系统通过订阅消息队列来监控优化进度。
    """
    def __init__(self, url:str):
        """
        初始化优化进度通知器
        
        @param url: 消息队列服务器URL地址
        """
        # 消息队列服务器URL
        self._url = url
        # 消息队列服务器对象
        self._server:WtMQServer = None

    def run(self):
        """
        启动消息队列服务器
        
        创建并启动消息队列服务器，准备接收和发送消息。
        """
        # 添加消息队列服务器
        self._server = mq.add_mq_server(self._url)

    def publish(self, topic:str, message:str):
        """
        发布消息到消息队列
        
        @param topic: 消息主题
        @param message: 消息内容（字符串格式）
        """
        # 如果服务器未启动，直接返回
        if self._server is None:
            return
        # 发布消息
        self._server.publish_message(topic, message)

    def on_start(self, pgroups:int):
        """
        通知优化开始事件
        
        @param pgroups: 参数组总数
        """
        # 构建开始事件数据
        data = {
            "pgroups":pgroups  # 参数组总数
        }
        # 发布开始事件消息
        self.publish("OPT_START", json.dumps(data))

    def on_stop(self, pgroups:int, elapse:int):
        """
        通知优化停止事件
        
        @param pgroups: 参数组总数
        @param elapse: 耗时（毫秒）
        """
        # 构建停止事件数据
        data = {
            "pgroups": pgroups,  # 参数组总数
            "elapse":int(elapse)  # 耗时（毫秒）
        }
        # 发布停止事件消息
        self.publish("OPT_STOP", json.dumps(data))

    def on_state(self, pgroups:int, done:int, progress:float, elapse:float):
        """
        通知优化状态更新事件
        
        @param pgroups: 参数组总数
        @param done: 已完成数量
        @param progress: 进度百分比
        @param elapse: 已耗时（毫秒）
        """
        # 构建状态更新数据
        data = {
            "pgroups": pgroups,    # 参数组总数
            "done": done,          # 已完成数量
            "progress":progress,   # 进度百分比
            "elapse":int(elapse)   # 已耗时（毫秒）
        }
        # 发布状态更新消息
        self.publish("OPT_STATE", json.dumps(data))

def ayalyze_result(strName:str, time_range:tuple, params:dict, capital = 5000000, rf = 0, period = 240):
    folder = "./outputs_bt/%s/" % (strName)
    df_closes = pd.read_csv(folder + "closes.csv")
    df_funds = pd.read_csv(folder + "funds.csv")

    df_wins = df_closes[df_closes["profit"]>0]
    df_loses = df_closes[df_closes["profit"]<=0]

    ay_WinnerBarCnts = df_wins["closebarno"]-df_wins["openbarno"]
    ay_LoserBarCnts = df_loses["closebarno"]-df_loses["openbarno"]

    total_winbarcnts = ay_WinnerBarCnts.sum()
    total_losebarcnts = ay_LoserBarCnts.sum()

    total_fee = df_funds.iloc[-1]["fee"]

    totaltimes = len(df_closes) # 总交易次数
    wintimes = len(df_wins)     # 盈利次数
    losetimes = len(df_loses)   # 亏损次数
    winamout = df_wins["profit"].sum()      #毛盈利
    loseamount = df_loses["profit"].sum()   #毛亏损
    trdnetprofit = winamout + loseamount    #交易净盈亏
    accnetprofit = trdnetprofit - total_fee #账户净盈亏
    winrate = wintimes / totaltimes if totaltimes>0 else 0      # 胜率
    avgprof = trdnetprofit/totaltimes if totaltimes>0 else 0    # 单次平均盈亏
    avgprof_win = winamout/wintimes if wintimes>0 else 0        # 单次盈利均值
    avgprof_lose = loseamount/losetimes if losetimes>0 else 0   # 单次亏损均值
    winloseratio = abs(avgprof_win/avgprof_lose) if avgprof_lose!=0 else "N/A"   # 单次盈亏均值比
        
    max_consecutive_wins = 0    # 最大连续盈利次数
    max_consecutive_loses = 0   # 最大连续亏损次数
    
    avg_bars_in_winner = total_winbarcnts/wintimes if wintimes>0 else "N/A"
    avg_bars_in_loser = total_losebarcnts/losetimes if losetimes>0 else "N/A"

    consecutive_wins = 0
    consecutive_loses = 0
    for idx, row in df_closes.iterrows():
        profit = row["profit"]
        if profit > 0:
            consecutive_wins += 1
            consecutive_loses = 0
        else:
            consecutive_wins = 0
            consecutive_loses += 1
        
        max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
        max_consecutive_loses = max(max_consecutive_loses, consecutive_loses)

    # 逐日绩效分析
    summary_by_day = summary_analyze(df_funds, capital, rf, period)

    summary = params.copy()
    summary["开始时间"] = time_range[0]
    summary["结束时间"] = time_range[1]
    summary["回测天数"] = summary_by_day["days"]
    summary["区间收益率%"] = summary_by_day["total_return"]
    summary["日胜率%"] = summary_by_day["win_rate"]
    summary["年化收益率%"] = summary_by_day["annual_return"]
    summary["最大回撤%"] = summary_by_day["max_falldown"]
    summary["Calmar"] = summary_by_day["calmar_ratio"]
    summary["Sharpe"] = summary_by_day["sharpe_ratio"]
    summary["总交易次数"] = totaltimes
    summary["盈利次数"] = wintimes
    summary["亏损次数"] = losetimes
    summary["毛盈利"] = float(winamout)
    summary["毛亏损"] = float(loseamount)
    summary["账户净盈亏"] = float(accnetprofit)
    summary["逐笔胜率%"] = winrate*100
    summary["逐笔平均盈亏"] = avgprof
    summary["逐笔平均净盈亏"] = accnetprofit/totaltimes
    summary["逐笔平均盈利"] = avgprof_win
    summary["逐笔逐笔亏损"] = avgprof_lose
    summary["逐笔盈亏比"] = winloseratio
    summary["最大连续盈利次数"] = max_consecutive_wins
    summary["最大连续亏损次数"] = max_consecutive_loses
    summary["平均盈利周期"] = avg_bars_in_winner
    summary["平均亏损周期"] = avg_bars_in_loser

    f = open(folder+"summary.json", mode="w")
    f.write(json.dumps(obj=summary, indent=4))
    f.close()

    return

def start_task_group(env_params, gpName:str, params:list, counter, capital = 5000000, rf = 0, period = 240, 
    strategy_type = None, cpp_stra_module = None, cpp_stra_type = None):
    '''
    启动多个回测任务，来回测一组参数，这里共用一个engine，因此可以避免多次io
    @params 参数组
    '''
    is_yaml = True
    fname = "./logcfg_tpl.yaml"
    if not os.path.exists(fname):
        is_yaml = True
        fname = "./logcfg_tpl.json"

    print(f"{gpName} 共有{len(params)}组参数，开始回测...")

    if not os.path.exists(fname):
        content = "{}"
    else:
        f = open(fname, "r")
        content =f.read()
        f.close()
        content = content.replace("$NAME$", gpName)
        if is_yaml:
            content = json.dumps(yaml.full_load(content))

    engine = WtBtEngine(eType=EngineType.ET_CTA, logCfg=content, isFile=False)
    # 配置类型的参数相对固定
    if env_params["iscfgfile"]:
        engine.init(env_params["deps_dir"], env_params["cfgfile"], 
            env_params["deps_files"]["commfile"], env_params["deps_files"]["contractfile"],
            env_params["deps_files"]["sessionfile"], env_params["deps_files"]["holidayfile"],
            env_params["deps_files"]["hotfile"], env_params["deps_files"]["secondfile"])
    else:
        engine.init_with_config(env_params["deps_dir"], env_params["cfgfile"],
            env_params["deps_files"]["commfile"], env_params["deps_files"]["contractfile"],
            env_params["deps_files"]["sessionfile"], env_params["deps_files"]["holidayfile"],
            env_params["deps_files"]["hotfile"], env_params["deps_files"]["secondfile"])
    engine.configBTStorage(mode=env_params["storage_type"], path=env_params["storage_path"], storage=env_params["storage"])
    # 遍历参数组
    total = len(params)
    cnt = 0
    for param in params:
        cnt += 1
        print(f"{gpName} 正在回测{cnt}/{total}")
        name = param["name"]
        
        engine.configBacktest(param["start_time"], param["end_time"])
        time_range = (param["start_time"], param["end_time"])
        # 去掉多余的参数
        param.pop("start_time")
        param.pop("end_time")
        if cpp_stra_module is not None:
            param.pop("name")
            engine.setExternalCtaStrategy(name, cpp_stra_module, cpp_stra_type, param)
        else:
            straInfo = strategy_type(**param)
            engine.set_cta_strategy(straInfo)
        engine.commitBTConfig()
        engine.run_backtest()
        ayalyze_result(name, time_range, param, capital, rf, period)
        counter.value += 1
    engine.release_backtest()

class ParamInfo:
    """
    参数信息类
    
    用于存储策略参数的配置信息，支持两种参数生成方式：
    1. 范围参数：指定起始值、结束值和步长，自动生成参数序列
    2. 列表参数：直接指定参数值列表
    """
    def __init__(self, name:str, start_val = None, end_val = None, step_val = None, ndigits = 1, val_list:list = None):
        """
        初始化参数信息
        
        @param name: 参数名称
        @param start_val: 起始值（范围参数）
        @param end_val: 结束值（范围参数）
        @param step_val: 变化步长（范围参数）
        @param ndigits: 小数位数，用于四舍五入
        @param val_list: 参数值列表（列表参数），如果指定则忽略范围参数
        """
        self.name = name          # 参数名称
        self.start_val = start_val  # 起始值
        self.end_val = end_val      # 结束值
        self.step_val = step_val    # 变化步长
        self.ndigits = ndigits      # 小数位数
        self.val_list = val_list    # 指定的参数值列表

    def gen_array(self):
        """
        生成参数值数组
        
        根据配置生成参数值数组。如果指定了val_list，则直接返回列表；
        否则根据start_val、end_val和step_val生成参数序列。
        
        @return: 参数值列表
        """
        # 如果指定了参数值列表，直接返回
        if self.val_list is not None:
            return self.val_list

        # 否则根据范围生成参数序列
        values = list()
        # 从起始值开始，四舍五入到指定小数位
        curVal = round(self.start_val, self.ndigits)
        # 循环生成参数值，直到达到或超过结束值
        while curVal < self.end_val:
            values.append(curVal)

            # 增加步长
            curVal += self.step_val
            # 四舍五入到指定小数位
            curVal = round(curVal, self.ndigits)
            # 如果达到或超过结束值，则设置为结束值并退出循环
            if curVal >= self.end_val:
                curVal = self.end_val
                break
        # 添加最后一个值（结束值）
        values.append(round(curVal, self.ndigits))
        return values

class WtCtaOptimizer:
    """
    CTA策略参数优化器类
    
    用于对CTA（Commodity Trading Advisor，商品交易顾问）策略进行参数优化，
    通过网格搜索的方式遍历参数空间，对每组参数进行回测，并分析回测结果，找出最优参数组合。
    支持多进程并行执行，提高优化效率。
    """
    def __init__(self, worker_num:int = 8, notifier:OptimizeNotifier = None):
        """
        初始化CTA策略参数优化器
        
        @param worker_num: 工作进程个数，默认为8，可以根据CPU核心数设置
        @param notifier: 优化进度通知器，用于实时通知优化进度，可选
        """
        # 工作进程数量
        self.worker_num = worker_num
        # 当前正在运行的工作进程数量
        self.running_worker = 0
        # 可变参数字典，存储需要优化的参数配置
        self.mutable_params = dict()
        # 固定参数字典，存储不需要优化的参数值
        self.fixed_params = dict()
        # 回测环境参数字典，存储回测配置信息
        self.env_params = dict()

        # C++策略模块路径（如果使用C++策略）
        self.cpp_stra_module = None
        # C++策略类型（如果使用C++策略）
        self.cpp_stra_type = None

        # 优化进度通知器
        self.notifier = notifier        
        return

    def add_mutable_param(self, name:str, start_val, end_val, step_val, ndigits = 1):
        '''
        添加可变参数\n

        @name       参数名\n
        @start_val  起始值\n
        @end_val    结束值\n
        @step_val   步长\n
        @ndigits    小数位
        '''
        self.mutable_params[name] = ParamInfo(name=name, start_val=start_val, end_val=end_val, step_val=step_val, ndigits=ndigits)

    def add_listed_param(self, name:str, val_list:list):
        '''
        添加限定范围的可变参数\n

        @name       参数名\n
        @val_list   参数值列表
        '''
        self.mutable_params[name] = ParamInfo(name=name, val_list=val_list)

    def add_fixed_param(self, name:str, val):
        '''
        添加固定参数\n

        @name       参数名\n
        @val        值\n
        '''
        self.fixed_params[name] = val
        return
    
    def set_strategy(self, typeName:type, name_prefix:str):
        '''
        设置策略\n

        @typeName       策略类名\n
        @name_prefix    命名前缀，用于自动命名用，一般为格式为"前缀_参数1名_参数1值_参数2名_参数2值"
        '''
        self.strategy_type = typeName
        self.name_prefix = name_prefix
        return

    def set_cpp_strategy(self, module:str, type_name:type, name_prefix:str):
        '''
        设置CPP策略\n

        @module         模块文件\n
        @typeName       策略类名\n
        @name_prefix    命名前缀，用于自动命名用，一般为格式为"前缀_参数1名_参数1值_参数2名_参数2值"
        '''
        self.cpp_stra_module = module
        self.cpp_stra_type = type_name
        self.name_prefix = name_prefix
        return

    def config_backtest_env(self, deps_dir:str, 
        cfgfile:str="configbt.yaml", 
        storage_type:str="csv", 
        storage_path:str = None, 
        storage:dict = None,
        commfile:str = None, 
        contractfile:str = None,
        sessionfile:str = None,
        holidayfile:str= None,
        hotfile:str = None,
        secondfile:str = None,
        iscfgfile:bool = True):
        '''
        配置回测环境\n

        @deps_dir   依赖文件目录\n
        @cfgfile    配置文件名\n
        @storage_type   存储类型，csv/bin等\n
        @storage_path   存储路径
        '''
        self.env_params["deps_dir"] = deps_dir
        self.env_params["deps_files"] = {
            "commfile":commfile,
            "contractfile":contractfile,
            "sessionfile":sessionfile,
            "holidayfile":holidayfile,
            "hotfile":hotfile,
            "secondfile":secondfile
        }
        
        self.env_params["cfgfile"] = cfgfile
        self.env_params["iscfgfile"] = iscfgfile
        self.env_params["storage_type"] = storage_type
        self.env_params["storage"] = storage
        self.env_params["storage_path"] = storage_path

    def config_backtest_time(self, start_time:int, end_time:int):
        '''
        配置回测时间，可多次调用配置多个回测时间区间\n

        @start_time 开始时间，精确到分钟，格式如201909100930\n
        @end_time   结束时间，精确到分钟，格式如201909100930
        '''
        if "time_ranges" not in self.env_params:
            self.env_params["time_ranges"] = []

        self.env_params["time_ranges"].append([start_time,end_time])

    def __gen_tasks__(self, markerfile:str = "strategies.json", order_by_field:str=""):
        '''
        生成回测任务
        '''
        param_names = self.mutable_params.keys()
        if order_by_field != "" and order_by_field in param_names:
            param_names = [order_by_field] + param_names.remove(order_by_field)

        param_values = dict()
        # 先生成各个参数的变量数组
        # 并计算总的参数有多少组
        total_groups = 1
        for name in param_names:
            paramInfo = self.mutable_params[name]
            values = paramInfo.gen_array()
            param_values[name] = values
            total_groups *= len(values)

        #再生成最终每一组的参数dict
        param_groups = list()
        stra_names = dict()
        time_ranges = self.env_params["time_ranges"]
        for time_range in time_ranges:
            start_time = time_range[0]
            end_time = time_range[1]
            for i in range(total_groups):
                k = i
                thisGrp = self.fixed_params.copy()  #复制固定参数
                endix = ''
                for name in param_names:
                    cnt = len(param_values[name])
                    curVal = param_values[name][k%cnt]
                    tname = type(curVal)
                    if tname.__name__ == "list":
                        val_str  = ''
                        for item in curVal:
                            val_str += str(item)
                            val_str += "_"

                        val_str = val_str[:-1]
                        thisGrp[name] = curVal
                        endix += name 
                        endix += "_"
                        endix += val_str
                        endix += "_"
                    else:
                        thisGrp[name] = curVal
                        endix += name 
                        endix += "_"
                        endix += str(curVal)
                        endix += "_"
                    k = math.floor(k / cnt)

                endix = endix[:-1]
                straName = self.name_prefix + endix
                straName += f"_{start_time}_{end_time}"
                thisGrp["name"] = straName
                thisGrp["start_time"] = start_time
                thisGrp["end_time"] = end_time
                stra_names[straName] = thisGrp
                param_groups.append(thisGrp)
        
        # 将每一组参数和对应的策略ID落地到文件中，方便后续的分析
        f = open(markerfile, "w")
        f.write(json.dumps(obj=stra_names, sort_keys=True, indent=4))
        f.close()
        return param_groups

    def go(self, order_by_field:str = "", out_marker_file:str = "strategies.json", out_summary_file:str = "total_summary.csv", capital = 5000000, rf = 0, period = 240):
        '''
        启动优化器\n
        @order_by_field     参数排序字段
        @markerfile         标记文件名，回测完成以后分析会用到
        '''
        self.tasks = self.__gen_tasks__(out_marker_file, order_by_field)
        if self.notifier is not None:
            self.notifier.on_start(len(self.tasks))
        
        stime = datetime.datetime.now()
        self.counter = multiprocessing.Manager().Value(ctypes.c_int, 0)
        pool = []
        total_size = len(self.tasks)
        gpSize = math.floor(total_size / self.worker_num)
        leftSz = total_size % self.worker_num
        if gpSize == 0:
            gpSize = 1
        work_id = 0
        max_cnt = min(self.worker_num,total_size)
        fromIdx = 0
        for i in range(max_cnt):
            work_id = i + 1
            work_name = f"Worker[{work_id}]"
            thisCnt = gpSize
            if leftSz > 0:
                thisCnt += 1
                leftSz -= 1

            params = self.tasks[fromIdx: fromIdx + thisCnt]
            p = multiprocessing.Process(
                target=start_task_group, 
                args=(self.env_params, work_name, params, self.counter, capital, rf, period, self.strategy_type, self.cpp_stra_module, self.cpp_stra_type), 
                name=work_name)
            p.start()
            print(f"{work_name} 开始工作")
            pool.append(p)

            fromIdx += thisCnt
        
        alive_cnt = len(pool)
        while alive_cnt > 0:
            for task in pool:
                if not task.is_alive():
                    pool.remove(task)
                    alive_cnt -= 1
                    print(f"{task.name} 结束工作了(剩余{alive_cnt})")

            if self.notifier is not None:
                elapse = datetime.datetime.now() - stime
                self.notifier.on_state(total_size, self.counter.value, self.counter.value*100/total_size, int(elapse.total_seconds()*1000))            
            time.sleep(0.5)

        #开始汇总回测结果
        f = open(out_marker_file, "r")
        content = f.read()
        f.close()

        obj_stras = json.loads(content)
        total_summary = list()
        for straName in obj_stras:
            filename = f"./outputs_bt/{straName}/summary.json"
            if not os.path.exists(filename):
                print(f"{filename}不存在，请检查数据")
                continue
                
            f = open(filename, "r")
            content = f.read()
            f.close()
            obj_summary = json.loads(content)
            total_summary.append(obj_summary)

        df_summary = df(total_summary)
        # df_summary = df_summary.drop(labels=["name"], axis='columns')
        df_summary.to_csv(out_summary_file, encoding='utf-8-sig')

        if self.notifier is not None:
            elapse = datetime.datetime.now() - stime
            self.notifier.on_stop(total_size, elapse.total_seconds()*1000) 

    def analyze(self, out_marker_file:str = "strategies.json", out_summary_file:str = "total_summary.csv"):
        #开始汇总回测结果
        f = open(out_marker_file, "r")
        content = f.read()
        f.close()

        total_summary = list()
        obj_stras = json.loads(content)
        for straName in obj_stras:
            params = obj_stras[straName]
            filename = f"./outputs_bt/{straName}/summary.json"
            if not os.path.exists(filename):
                print("%s不存在，请检查数据" % (filename))
                continue
                
            time_range = (params["start_time"],params["end_time"])
            self.__ayalyze_result__(straName, time_range, params)
            
            f = open(filename, "r")
            content = f.read()
            f.close()
            obj_summary = json.loads(content)
            total_summary.append(obj_summary)

        df_summary = df(total_summary)
        df_summary = df_summary.drop(labels=["name"], axis='columns')
        df_summary.to_csv(out_summary_file)

    def analyzer(self, out_marker_file:str = "strategies.json", init_capital=500000, rf=0.02, annual_trading_days=240):
        for straname in json.load(open(out_marker_file, mode='r')).keys():
            try:
                analyst = WtBtAnalyst()
                analyst.add_strategy(straname, folder=f"./outputs_bt/{straname}/", init_capital=init_capital, rf=rf, annual_trading_days=annual_trading_days)
                analyst.run()
            except:
                pass