"""
WonderTrader回测查探器模块

该模块提供了基于Web的回测结果查看和分析功能，通过FastAPI提供RESTful API接口。
支持查看回测结果、分析交易数据、查看K线图表等功能。

主要功能：
1. 工作空间管理：管理多个回测工作空间
2. 回测结果查看：查看回测的资金曲线、交易记录、交易回合等
3. 交易数据分析：分析交易的胜率、盈亏比、最大回撤等指标
4. K线数据查询：查询回测使用的K线数据
5. Web界面：提供Web界面进行可视化查看和分析

设计模式：
- 使用FastAPI提供RESTful API接口
- 使用Pandas和NumPy进行数据分析
- 使用文件系统存储工作空间配置
"""

import os
import json
import hashlib
import datetime
import pytz
from fastapi import FastAPI, Body
from starlette.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import pandas as pd
import numpy as np

from wtpy import WtDtServo


def do_trading_analyze(df_closes, df_funds):
    """
    交易数据分析函数
    
    对回测的交易数据进行统计分析，计算各种性能指标。
    使用Pandas DataFrame进行数据处理和计算。
    
    @param df_closes: 交易回合DataFrame，包含每笔交易的详细信息（开仓时间、平仓时间、盈亏等）
    @param df_funds: 资金曲线DataFrame，包含每日的资金变化（日期、权益、盈亏等）
    @return: 分析结果字典，包含各种性能指标
    """
    # 筛选盈利交易和亏损交易
    df_wins = df_closes[df_closes["profit"] > 0]  # 盈利交易
    df_loses = df_closes[df_closes["profit"] <= 0]  # 亏损交易

    # 计算盈利和亏损交易的持仓K线根数
    ay_WinnerBarCnts = df_wins["closebarno"] - df_wins["openbarno"]  # 盈利交易的持仓K线根数
    ay_LoserBarCnts = df_loses["closebarno"] - df_loses["openbarno"]  # 亏损交易的持仓K线根数
    total_winbarcnts = ay_WinnerBarCnts.sum()  # 盈利交易的总持仓K线根数
    total_losebarcnts = ay_LoserBarCnts.sum()  # 亏损交易的总持仓K线根数

    # 计算总手续费
    total_fee = df_closes['fee'].sum()

    # 计算交易次数统计
    totaltimes = len(df_closes)  # 总交易次数
    wintimes = len(df_wins)  # 盈利次数
    losetimes = len(df_loses)  # 亏损次数
    winamout = float(df_wins["profit"].sum())  # 毛盈利（所有盈利交易的盈利总和）
    loseamount = float(df_loses["profit"].sum())  # 毛亏损（所有亏损交易的亏损总和）
    trdnetprofit = winamout + loseamount  # 交易净盈亏（盈利+亏损，亏损为负数）
    accnetprofit = trdnetprofit - total_fee  # 账户净盈亏（扣除手续费后的净盈亏）
    winrate = (wintimes / totaltimes) if totaltimes > 0 else 0  # 胜率（盈利次数/总次数）
    avgprof = (trdnetprofit / totaltimes) if totaltimes > 0 else 0  # 单次平均盈亏
    avgprof_win = (winamout / wintimes) if wintimes > 0 else 0  # 单次盈利均值
    avgprof_lose = (loseamount / losetimes) if losetimes > 0 else 0  # 单次亏损均值
    winloseratio = abs(avgprof_win / avgprof_lose) if avgprof_lose != 0 else "N/A"  # 单次盈亏均值比（盈利均值/亏损均值的绝对值）

    # 计算最大盈利和最大亏损
    largest_profit = float(df_wins['profit'].max())  # 单笔最大盈利交易
    largest_loss = float(df_loses['profit'].min())  # 单笔最大亏损交易（最小值为最大亏损）
    # 计算交易的平均持仓K线根数
    avgtrd_hold_bar = 0 if totaltimes==0 else ((df_closes['closebarno'] - df_closes['openbarno']).sum()) / totaltimes
    # 计算平均空仓K线根数（两笔交易之间的空仓K线根数）
    avb = (df_closes['openbarno'] - df_closes['closebarno'].shift(1).fillna(value=0))
    avgemphold_bar = 0 if len(df_closes)==0 else avb.sum() / len(df_closes)

    # 计算两笔盈利交易之间的平均空仓K线根数
    win_holdbar_situ = (df_wins['openbarno'].shift(-1) - df_wins['closebarno']).dropna()
    winempty_avgholdbar = 0 if len(df_wins)== 0 or len(df_wins) == 1 else win_holdbar_situ.sum() / (len(df_wins)-1)
    # 计算两笔亏损交易之间的平均空仓K线根数
    loss_holdbar_situ = (df_loses['openbarno'].shift(-1) - df_loses['closebarno']).dropna()
    lossempty_avgholdbar = 0 if len(df_loses)== 0 or len(df_loses) == 1 else loss_holdbar_situ.sum() / (len(df_loses)-1)
    # 初始化最大连续盈利和亏损次数
    max_consecutive_wins = 0  # 最大连续盈利次数
    max_consecutive_loses = 0  # 最大连续亏损次数

    # 计算盈利和亏损交易的平均持仓K线根数
    avg_bars_in_winner = total_winbarcnts / wintimes if wintimes > 0 else "N/A"
    avg_bars_in_loser = total_losebarcnts / losetimes if losetimes > 0 else "N/A"

    # 初始化连续盈利和亏损计数器
    consecutive_wins = 0
    consecutive_loses = 0

    # 遍历所有交易，计算最大连续盈利和亏损次数
    for idx, row in df_closes.iterrows():
        profit = row["profit"]
        if profit > 0:
            # 如果盈利，增加连续盈利计数，重置连续亏损计数
            consecutive_wins += 1
            consecutive_loses = 0
        else:
            # 如果亏损，重置连续盈利计数，增加连续亏损计数
            consecutive_wins = 0
            consecutive_loses += 1

        # 更新最大连续盈利和亏损次数
        max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
        max_consecutive_loses = max(max_consecutive_loses, consecutive_loses)

    # 创建分析结果字典
    summary = dict()

    # 填充分析结果
    summary["total_trades"] = totaltimes  # 总交易次数
    summary["profit"] = float(winamout)  # 毛盈利
    summary["loss"] = float(loseamount)  # 毛亏损
    summary["net_profit"] = float(trdnetprofit)  # 交易净盈亏
    summary["fee"] = total_fee  # 总手续费
    summary["accnet_profit"] = 0 if totaltimes == 0 else accnetprofit  # 账户净盈亏
    summary["winrate"] = winrate * 100  # 胜率（转换为百分比）
    summary["avgprof"] = avgprof  # 单次平均盈亏
    summary["avgprof_win"] = avgprof_win  # 单次盈利均值
    summary["avgprof_lose"] = avgprof_lose  # 单次亏损均值
    summary["winloseratio"] = winloseratio  # 单次盈亏均值比
    summary["largest_profit"] = largest_profit  # 单笔最大盈利
    summary["largest_loss"] = largest_loss  # 单笔最大亏损
    summary["avgtrd_hold_bar"] = avgtrd_hold_bar  # 交易的平均持仓K线根数
    summary["avgemphold_bar"] = avgemphold_bar  # 平均空仓K线根数
    summary["winempty_avgholdbar"] = winempty_avgholdbar  # 两笔盈利交易之间的平均空仓K线根数
    summary["lossempty_avgholdbar"] = lossempty_avgholdbar  # 两笔亏损交易之间的平均空仓K线根数
    summary["avg_bars_in_winner"] = avg_bars_in_winner  # 盈利交易的平均持仓K线根数
    summary["avg_bars_in_loser"] = avg_bars_in_loser  # 亏损交易的平均持仓K线根数
    summary["max_consecutive_wins"] = max_consecutive_wins  # 最大连续盈利次数
    summary["max_consecutive_loses"] = max_consecutive_loses  # 最大连续亏损次数

    # 返回分析结果
    return summary


class WtBtSnooper:
    """
    回测查探器类
    
    提供基于Web的回测结果查看和分析功能，通过FastAPI提供RESTful API接口。
    支持管理多个工作空间，查看回测结果，分析交易数据等。
    
    主要功能：
    1. 工作空间管理：添加、删除、查询工作空间
    2. 回测结果查看：查看回测的资金曲线、交易记录、交易回合等
    3. 交易数据分析：分析交易的胜率、盈亏比、最大回撤等指标
    4. K线数据查询：查询回测使用的K线数据
    5. Web服务器：提供Web界面和API接口
    """
    
    def __init__(self, dtServo:WtDtServo = None):
        """
        初始化回测查探器
        
        创建回测查探器实例，设置数据服务器，并加载工作空间配置。
        
        @param dtServo: 数据服务器实例（WtDtServo，默认None），用于提供历史数据服务
        """
        # 工作空间路径（当前未使用）
        self.path = ""
        # 数据服务器引用
        self.dt_servo = dtServo
        # 工作空间列表，每个工作空间包含id、name、path等信息
        self.workspaces = list()

        # 静态文件夹列表，用于配置Web服务器的静态文件服务
        self.static_folders = list()

        # 加载工作空间配置数据
        self.load_data()

    def load_data(self):
        """
        加载工作空间配置数据
        
        从data.json文件加载工作空间配置。
        如果文件不存在或内容为空，则直接返回。
        """
        # 如果配置文件不存在，直接返回
        if not os.path.exists("data.json"):
            return

        # 读取配置文件内容
        f = open("data.json")
        content = f.read()
        f.close()

        # 如果文件内容为空，直接返回
        if len(content) == 0:
            return

        # 解析JSON内容
        obj =  json.loads(content)
        # 如果包含工作空间配置，加载工作空间列表
        if "workspace" in obj:
            self.workspaces = obj["workspace"]

    def save_data(self):
        """
        保存工作空间配置数据
        
        将工作空间配置保存到data.json文件。
        """
        # 创建配置对象
        obj =  {
            "workspace": self.workspaces
        }
        # 将配置对象转换为JSON字符串
        content = json.dumps(obj, ensure_ascii=False, indent=4)
        # 写入配置文件
        f = open("data.json", "w")
        f.write(content)
        f.close() 

    def add_static_folder(self, folder:str, path:str = "/static", name:str = "static"):
        """
        添加静态文件夹
        
        添加一个静态文件夹到Web服务器，用于提供静态文件服务。
        
        @param folder: 文件夹路径（字符串），静态文件的物理路径
        @param path: URL路径（字符串，默认"/static"），静态文件的URL路径
        @param name: 名称（字符串，默认"static"），静态文件服务的名称
        """
        # 将静态文件夹配置添加到列表
        self.static_folders.append({
            "path": path,  # URL路径
            "folder": folder,  # 物理路径
            "name": name  # 服务名称
        })

    def __server_impl__(self, port:int, host:str):
        """
        服务器实现方法（私有方法）
        
        启动uvicorn Web服务器。
        
        @param port: 端口号（整数），服务器监听的端口
        @param host: 主机地址（字符串），服务器绑定的主机地址
        """
        # 使用uvicorn运行FastAPI应用
        uvicorn.run(self.server_inst, port = port, host = host)

    def run_as_server(self, port:int = 8081, host="127.0.0.1", bSync:bool = True):
        """
        以服务器模式运行
        
        创建FastAPI应用，注册API路由，并启动Web服务器。
        可以同步运行（阻塞）或异步运行（后台线程）。
        
        @param port: 端口号（整数，默认8081），服务器监听的端口
        @param host: 主机地址（字符串，默认"127.0.0.1"），服务器绑定的主机地址
        @param bSync: 是否同步运行（布尔值，默认True），True表示阻塞运行，False表示后台线程运行
        """
        # 定义API标签信息
        tags_info = [
            {"name":"Backtest APIs","description":"回测查探器接口"}
        ]

        # 创建FastAPI应用实例
        app = FastAPI(title="WtBtSnooper", description="A simple http api of WtBtSnooper", openapi_tags=tags_info, redoc_url=None, version="1.0.0")
        # 添加GZip压缩中间件，压缩大于1000字节的响应
        app.add_middleware(GZipMiddleware, minimum_size=1000)
        # 添加会话中间件，用于管理用户会话
        app.add_middleware(SessionMiddleware, secret_key='!@#$%^&*()', max_age=25200, session_cookie='WtBtSnooper_sid')

        # 如果配置了静态文件夹，挂载静态文件服务
        if len(self.static_folders) > 0:
            for static_item in self.static_folders:
                app.mount(static_item["path"], StaticFiles(directory = static_item["folder"]), name=static_item["name"])
        else:
            # 如果没有配置静态文件夹，使用默认的静态文件夹
            paths = os.path.split(__file__)
            a = (paths[:-1] + ("static/console",))
            path = os.path.join(*a)
            app.mount("/backtest", StaticFiles(directory = path), name="static")

        # 保存FastAPI应用实例
        self.server_inst = app

        # 初始化回测API路由
        self.init_bt_apis(app)

        # 根据bSync参数决定运行方式
        if bSync:
            # 同步运行（阻塞）
            self.__server_impl__(port, host)
        else:
            # 异步运行（后台线程）
            import threading
            self.worker = threading.Thread(target=self.__server_impl__, args=(port,host,))
            self.worker.setDaemon(True)
            self.worker.start()

    def get_workspace_path(self, id:str) ->str:
        """
        获取工作空间路径
        
        根据工作空间ID查找对应的工作空间路径。
        
        @param id: 工作空间ID（字符串），要查找的工作空间标识
        @return: 工作空间路径（字符串），如果未找到则返回空字符串
        """
        # 遍历所有工作空间
        for wInfo in self.workspaces:
            # 如果ID匹配，返回路径
            if wInfo["id"] == id:
                return wInfo["path"]
                
        return ""

    def init_bt_apis(self, app:FastAPI):
        """
        初始化回测API路由
        
        注册所有回测相关的API路由，包括工作空间管理、回测结果查询等。
        
        @param app: FastAPI应用实例，用于注册路由
        """
        # ========== 根路径重定向 ==========
        @app.get("/")
        async def console_entry():
            """
            控制台入口路由
            
            重定向到回测Web界面。
            """
            return RedirectResponse("/backtest/backtest.html")

        # ========== 工作空间管理API ==========
        @app.post("/bt/qryws", tags=["Backtest APIs"], description="获取工作空间")
        async def qry_workspaces():
            """
            查询工作空间列表
            
            返回所有工作空间的列表。
            """
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"Ok",  # 结果消息
                "workspaces": self.workspaces  # 工作空间列表
            }                

            return ret

        @app.post("/bt/addws", tags=["Backtest APIs"], description="添加工作空间")
        async def add_workspace(
            path:str = Body(..., title="工作空间路径", embed=True),
            name:str = Body(..., title="工作空间名称", embed=True)
        ):
            """
            添加工作空间
            
            添加一个新的工作空间，生成唯一ID并保存配置。
            
            @param path: 工作空间路径（字符串），回测结果文件的路径
            @param name: 工作空间名称（字符串），工作空间的显示名称
            """
            # 创建MD5哈希对象
            md5 = hashlib.md5()
            # 获取当前UTC时间并格式化为字符串
            now = datetime.datetime.now().replace(tzinfo=pytz.timezone('UTC')).strftime("%Y.%m.%d %H:%M:%S")
            # 计算MD5哈希值作为工作空间ID
            md5.update(now.encode("UTF8"))
            id = md5.hexdigest()
            # 添加工作空间到列表
            self.workspaces.append({
                "name": name,  # 工作空间名称
                "path": path,  # 工作空间路径
                "id": id  # 工作空间ID
            })

            # 按名称排序工作空间列表
            self.workspaces.sort(key=lambda x: x["name"])

            # 保存配置
            self.save_data()

            return {
                "result":0,
                "message":"Ok"
            }

        @app.post("/bt/delws", tags=["Backtest APIs"], description="删除工作空间")
        async def del_workspace(
            wsid:str = Body(..., title="工作空间ID", embed=True)
        ):
            """
            删除工作空间
            
            从工作空间列表中删除指定的工作空间。
            
            @param wsid: 工作空间ID（字符串），要删除的工作空间标识
            """
            # 遍历所有工作空间
            for wInfo in self.workspaces:
                # 如果ID匹配，删除工作空间
                if wInfo["id"] == wsid:
                    self.workspaces.remove(wInfo)
                    # 保存配置
                    self.save_data()
                    break

            return {
                "result":0,
                "message":"Ok"
            }

        # ========== 回测数据查询API ==========
        @app.post("/bt/qrybtstras", tags=["Backtest APIs"], description="读取全部回测策略")
        def qry_stra_bt_strategies(
            wsid:str = Body(..., title="工作空间ID", embed=True)
        ):
            """
            查询回测策略列表
            
            查询指定工作空间下的所有回测策略。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "strategies": self.get_all_strategy(path)  # 策略列表
            }
            return ret

        @app.post("/bt/qrybars", tags=["Backtest APIs"], description="获取K线")
        async def qry_bt_bars(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测K线数据
            
            查询指定策略的回测K线数据，包括K线数据、指标数据和标记数据。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 获取K线数据、指标数据和标记数据
            code, bars, index, marks = self.get_bt_kline(path, straid)
            # 如果K线数据为空，返回错误
            if bars is None:
                ret = {
                    "result":-2,  # 结果码，-2表示数据未找到
                    "message":"Data not found"  # 错误消息
                }
            else:
                # 构建成功响应
                ret = {
                    "result":0,  # 结果码，0表示成功
                    "message":"Ok",  # 结果消息
                    "bars": bars,  # K线数据列表
                    "code": code  # 合约代码
                }

                # 如果指标数据不为空，添加到响应中
                if index is not None:
                    ret["index"] = index

                # 如果标记数据不为空，添加到响应中
                if marks is not None:
                    ret["marks"] = marks

            return ret

    
        @app.post("/bt/qrybtsigs", tags=["Backtest APIs"], description="读取信号明细")
        def qry_stra_bt_signals(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测信号数据
            
            查询指定策略的回测信号数据（如条件单触发等）。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "signals":self.get_bt_signals(path, straid)  # 信号数据列表
            }
                    
            return ret

        @app.post("/bt/qrybttrds", tags=["Backtest APIs"], description="读取成交明细")
        def qry_stra_bt_trades(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测成交数据
            
            查询指定策略的回测成交记录数据。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "trades":self.get_bt_trades(path, straid)  # 成交数据列表
            }
                    
            return ret

        @app.post("/bt/qrybtfunds", tags=["Backtest APIs"], description="读取资金明细")
        def qry_stra_bt_funds(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测资金曲线数据
            
            查询指定策略的回测资金曲线数据。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "funds":self.get_bt_funds(path, straid)  # 资金曲线数据列表
            }
                    
            return ret

        @app.post("/bt/qrybtrnds", tags=["Backtest APIs"], description="读取回合明细")
        def qry_stra_bt_rounds(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测交易回合数据
            
            查询指定策略的回测交易回合数据（一次完整的开仓到平仓过程）。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "rounds":self.get_bt_rounds(path, straid)  # 交易回合数据列表
            }
            return ret

        @app.post("/bt/qrybtinfo", tags=["Backtest APIs"], description="读取回测信息")
        def qry_stra_bt_info(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测信息
            
            查询指定策略的回测摘要信息和环境信息。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "info":self.get_bt_info(path, straid)  # 回测信息字典（包含摘要和环境信息）
            }
            return ret

        @app.post("/bt/qrybtcloses", tags=["Backtest APIs"], description="读取成交数据")
        def qry_stra_bt_closes(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测成交数据（分类）
            
            查询指定策略的回测成交数据，按多仓、空仓、全部、月度、年度分类返回。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 获取分类的成交数据
            closes_data = self.get_bt_closes(path, straid)
            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "closes_long":closes_data[0],  # 多仓成交数据
                "closes_short":closes_data[1],  # 空仓成交数据
                "closes_all":closes_data[2],  # 全部成交数据
                "closes_month": closes_data[3],  # 月度成交数据
                "closes_year": closes_data[4]  # 年度成交数据
            }
            return ret

        @app.post("/bt/qrybtanalysis", tags=["Backtest APIs"], description="读取策略分析")
        def qry_stra_bt_analysis(
            wsid:str = Body(..., title="工作空间ID", embed=True),
            straid:str = Body(..., title="策略ID", embed=True)
        ):
            """
            查询回测策略分析数据
            
            查询指定策略的回测分析数据，包括全部、多仓、空仓的分析结果。
            
            @param wsid: 工作空间ID（字符串），要查询的工作空间标识
            @param straid: 策略ID（字符串），要查询的策略标识
            """
            # 获取工作空间路径
            path = self.get_workspace_path(wsid)
            # 如果路径为空，返回错误
            if len(path) == 0:
                ret = {
                    "result":-1,  # 结果码，-1表示失败
                    "message":"Invalid workspace"  # 错误消息
                }

            # 构建成功响应
            ret = {
                "result":0,  # 结果码，0表示成功
                "message":"OK",  # 结果消息
                "analysis":self.get_bt_analysis(path, straid)  # 分析结果字典（包含全部、多仓、空仓的分析）
            }
            return ret

    # ========== 数据读取方法 ==========
    def get_all_strategy(self, path) -> list:
        """
        获取所有策略列表
        
        扫描工作空间路径下的所有文件夹，每个文件夹代表一个策略。
        
        @param path: 工作空间路径（字符串），要扫描的路径
        @return: 策略名称列表
        """
        # 列出路径下的所有文件和文件夹
        files = os.listdir(path)
        # 创建返回列表
        ret = list()
        # 遍历所有文件和文件夹
        for filename in files:
            # 构建完整路径
            filepath = os.path.join(path, filename)
            # 如果是文件夹，添加到列表（文件夹代表一个策略）
            if os.path.isdir(filepath):
                ret.append(filename)
        return ret

    def get_bt_info(self, path:str, straid:str) -> dict:
        """
        获取回测信息
        
        读取回测的摘要信息和环境信息。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 回测信息字典，包含摘要和环境信息，如果文件不存在则返回None
        """
        # 构建摘要JSON文件路径
        filename = f"{straid}/summary.json"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取摘要文件内容
        f = open(filename, 'r')
        content = f.read()
        f.close()
        # 解析JSON内容
        summary = json.loads(content)

        # 构建环境JSON文件路径
        filename = f"{straid}/btenv.json"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取环境文件内容
        f = open(filename, 'r')
        content = f.read()
        f.close()
        # 解析JSON内容
        env = json.loads(content)

        # 返回回测信息字典
        return {
            'summary': summary,  # 摘要信息（性能指标等）
            'env': env  # 环境信息（回测参数等）
        }

    def get_bt_analysis(self, path: str, straid: str) -> dict:
        """
        获取回测分析数据
        
        读取回测的资金曲线和交易回合数据，进行统计分析。
        分别分析全部交易、多仓交易、空仓交易的性能指标。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 分析结果字典，包含全部、多仓、空仓的分析结果，如果文件不存在则返回None
        """
        # 构建资金曲线CSV文件路径
        funds_filename = f"{straid}/funds.csv"
        funds_filename = os.path.join(path,funds_filename)
        # 构建交易回合CSV文件路径
        closes_filename = f"{straid}/closes.csv"
        closes_filename = os.path.join(path,closes_filename)

        # 如果文件不存在，返回None
        if not (os.path.exists(funds_filename) or os.path.exists(closes_filename)):
            return None

        # 使用Pandas读取CSV文件
        df_funds = pd.read_csv(funds_filename)  # 资金曲线DataFrame
        df_closes = pd.read_csv(closes_filename)  # 交易回合DataFrame
        # 计算手续费（通过总盈亏的差值计算）
        df_closes['fee'] = df_closes['profit'] - df_closes['totalprofit'] + df_closes['totalprofit'].shift(1).fillna(
            value=0)
        # 筛选多仓交易和空仓交易
        df_long = df_closes[df_closes['direct'].apply(lambda x: 'LONG' in x)]  # 多仓交易
        df_short = df_closes[df_closes['direct'].apply(lambda x: 'SHORT' in x)]  # 空仓交易

        # 分别分析全部、多仓、空仓的交易数据
        summary_all = do_trading_analyze(df_closes, df_funds)  # 全部交易分析
        summary_short = do_trading_analyze(df_short, df_funds)  # 空仓交易分析
        summary_long = do_trading_analyze(df_long, df_funds)  # 多仓交易分析

        # 返回分析结果字典
        return {
            'summary_all': summary_all,  # 全部交易分析结果
            'summary_short': summary_short,  # 空仓交易分析结果
            'summary_long': summary_long  # 多仓交易分析结果
        }

    def get_bt_funds(self, path:str, straid:str) -> list:
        """
        获取回测资金曲线数据
        
        读取回测的资金曲线CSV文件，解析为字典列表。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 资金曲线数据列表，每个元素包含日期、平仓盈亏、浮动盈亏、动态权益、手续费等信息
        """
        # 构建资金曲线CSV文件路径
        filename = f"{straid}/funds.csv"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建资金数据列表
        funds = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建资金数据项
            tItem = {
                "date": int(cells[0]),  # 日期
                "closeprofit": float(cells[1]),  # 平仓盈亏
                "dynprofit": float(cells[2]),  # 浮动盈亏
                "dynbalance": float(cells[3]),  # 动态权益
                "fee": 0  # 手续费，默认为0
            }

            # 如果单元格数量大于4，读取手续费
            if len(cells) > 4:
                tItem["fee"] = float(cells[4])

            # 添加到资金数据列表
            funds.append(tItem)
        
        return funds

    def get_bt_closes(self, path:str, straid:str):
        """
        获取回测成交数据（分类）
        
        读取回测的交易回合数据，按多仓、空仓、全部、月度、年度分类处理。
        计算累计盈亏、回撤、收益率等指标。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 元组，包含多仓成交数据、空仓成交数据、全部成交数据、月度成交数据、年度成交数据
        """
        # 构建摘要JSON文件路径
        summary_file = f"{straid}/summary.json"
        summary_file = os.path.join(path, summary_file)
        # 构建交易回合CSV文件路径
        closes_file = f"{straid}/closes.csv"
        closes_file = os.path.join(path, closes_file)
        # 如果文件不存在，返回None
        if not (os.path.exists(closes_file) or os.path.exists(summary_file)):
            return None

        # 读取摘要文件，获取初始资金
        f = open(summary_file, 'r')
        content = f.read()
        f.close()
        summary = json.loads(content)
        capital = summary["capital"]  # 初始资金
        
        # 使用Pandas读取交易回合CSV文件
        df_closes = pd.read_csv(closes_file)
        df_closes = df_closes.copy()
        # 计算手续费（通过总盈亏的差值计算）
        df_closes['fee'] = df_closes['profit'] - df_closes['totalprofit'] + df_closes['totalprofit'].shift(1).fillna(
            value=0)
        # 计算扣除手续费后的盈亏
        df_closes['profit'] = df_closes['profit'] - df_closes['fee']
        # 计算累计盈亏
        df_closes['profit_sum'] = df_closes['profit'].expanding(1).sum()
        # 计算回撤（当前累计盈亏与历史最大累计盈亏的差值）
        df_closes['Withdrawal'] = df_closes['profit_sum'] - df_closes['profit_sum'].expanding(1).max()
        # 计算收益率（累计盈亏/初始资金 * 100）
        df_closes['profit_ratio'] = 100 * df_closes['profit_sum'] / capital
        # 计算回撤率
        withdrawal_ratio = []
        sim_equity = df_closes['profit_sum'] + capital  # 模拟权益
        for i in range(len(df_closes)):
            withdrawal_ratio.append(100 * (sim_equity[i] / sim_equity[:i + 1].max() - 1))
        df_closes['Withdrawal_ratio'] = withdrawal_ratio
        
        # ========== 处理全部成交数据 ==========
        # 将DataFrame转换为NumPy数组再转换为列表
        np_trade = np.array(df_closes).tolist()
        closes_all = list()
        # 遍历所有交易回合，转换为字典格式
        for item in np_trade:
            litem = {
                "opentime":int(item[2]),  # 开仓时间
                "closetime":int(item[4]),  # 平仓时间
                "profit":float(item[7]),  # 盈亏
                "direct":str(item[1]),  # 交易方向
                "openprice":float(item[3]),  # 开仓价格
                "closeprice":float(item[5]),  # 平仓价格
                "maxprofit":float(item[8]),  # 最大盈利
                "maxloss":float(item[9]),  # 最大亏损
                "qty":int(item[6]),  # 交易数量
                "capital": capital,  # 初始资金
                'profit_sum':float(item[16]),  # 累计盈亏
                'Withdrawal':float(item[17]),  # 回撤
                'profit_ratio':float(item[18]),  # 收益率
                'Withdrawal_ratio':float(item[19])  # 回撤率
            }
            closes_all.append(litem)
        
        # ========== 处理月度成交数据 ==========
        # 将平仓时间转换为datetime对象
        df_closes['time'] = df_closes['closetime'].apply(lambda x: datetime.datetime.strptime(str(x), '%Y%m%d%H%M'))
        # 按月度重采样，汇总月度数据
        df_c_m = df_closes.resample(rule='M', on='time', label='right',
                                                                 closed='right').agg({
            'profit': 'sum',  # 月度总盈亏
            'maxprofit': 'sum',  # 月度最大盈利
            'maxloss': 'sum',  # 月度最大亏损
        })
        df_c_m = df_c_m.reset_index()
        # 计算月度累计权益
        df_c_m['equity'] = df_c_m['profit'].expanding(1).sum() + capital
        # 计算月度收益率
        df_c_m['monthly_profit'] = 100 * (df_c_m['equity'] / df_c_m['equity'].shift(1).fillna(value=capital) - 1)
        closes_month = list()
        np_m = np.array(df_c_m).tolist()
        # 遍历月度数据，转换为字典格式
        for item in np_m:
            litem = {
                "time":int(item[0].strftime('%Y%m')),  # 月份（格式如202301）
                "profit":float(item[1]),  # 月度盈亏
                'maxprofit':float(item[2]),  # 月度最大盈利
                'maxloss':float(item[3]),  # 月度最大亏损
                'equity':float(item[4]),  # 月度权益
                'monthly_profit':float(item[5])  # 月度收益率
            }
            closes_month.append(litem)

        # ========== 处理年度成交数据 ==========
        # 按年度重采样，汇总年度数据
        df_c_y = df_closes.resample(rule='Y', on='time', label='right',
                                    closed='right').agg({
            'profit': 'sum',  # 年度总盈亏
            'maxprofit': 'sum',  # 年度最大盈利
            'maxloss': 'sum',  # 年度最大亏损
        })
        df_c_y = df_c_y.reset_index()
        # 计算年度累计权益
        df_c_y['equity'] = df_c_y['profit'].expanding(1).sum() + capital
        # 计算年度收益率
        df_c_y['monthly_profit'] = 100 * (df_c_y['equity'] / df_c_y['equity'].shift(1).fillna(value=capital) - 1)
        closes_year = list()
        np_y = np.array(df_c_y).tolist()
        # 遍历年度数据，转换为字典格式
        for item in np_y:
            litem = {
                "time":int(item[0].strftime('%Y%m')),  # 年份（格式如202301，实际是年份）
                "profit":float(item[1]),  # 年度盈亏
                'maxprofit':float(item[2]),  # 年度最大盈利
                'maxloss':float(item[3]),  # 年度最大亏损
                'equity':float(item[4]),  # 年度权益
                'annual_profit':float(item[5])  # 年度收益率
            }
            closes_year.append(litem)

        # ========== 处理多仓和空仓成交数据 ==========
        # 筛选多仓和空仓交易
        df_long = df_closes[df_closes['direct'].apply(lambda x: 'LONG' in x)]  # 多仓交易
        df_short = df_closes[df_closes['direct'].apply(lambda x: 'SHORT' in x)]  # 空仓交易
        df_long = df_long.copy()
        df_short = df_short.copy()
        # 计算多仓累计盈亏（扣除手续费）
        df_long["long_profit"] = df_long["profit"].expanding(1).sum()-df_long["fee"].expanding(1).sum()
        closes_long = list()
        closes_short = list()
        # 处理多仓数据
        np_long = np.array(df_long).tolist()
        for item in np_long:
            litem = {
                "date":int(item[4]),  # 平仓日期
                "long_profit":float(item[-1]),  # 多仓累计盈亏
                "capital":capital  # 初始资金
            }
            closes_long.append(litem)
        # 计算空仓累计盈亏（扣除手续费）
        df_short["short_profit"] = df_short["profit"].expanding(1).sum()-df_short["fee"].expanding(1).sum()
        # 处理空仓数据
        np_short = np.array(df_short).tolist()
        for item in np_short:
            litem = {
                "date":int(item[4]),  # 平仓日期
                "short_profit":float(item[-1]),  # 空仓累计盈亏
                "capital":capital  # 初始资金
            }
            closes_short.append(litem)

        # 返回分类的成交数据
        return closes_long, closes_short, closes_all, closes_month, closes_year

    def get_bt_trades(self, path:str, straid:str) -> list:
        """
        获取回测交易记录数据
        
        读取回测的交易记录CSV文件，解析为字典列表。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 交易记录数据列表，每个元素包含合约代码、时间、方向、开平、价格、数量、标记、手续费等信息
        """
        # 构建交易记录CSV文件路径
        filename = f"{straid}/trades.csv"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建交易记录列表
        items = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建交易记录项
            item = {
                "code": cells[0],  # 合约代码
                "time": int(cells[1]),  # 交易时间
                "direction": cells[2],  # 交易方向（买入/卖出）
                "offset": cells[3],  # 开平标志（开仓/平仓）
                "price": float(cells[4]),  # 成交价格
                "volume": float(cells[5]),  # 成交数量
                "tag": cells[6],  # 用户标记
                "fee": 0  # 手续费，默认为0
            }

            # 如果单元格数量大于7，读取手续费
            if len(cells) > 7:
                item["fee"] = float(cells[7])

            # 注意：这里代码有重复，如果单元格数量大于4也会设置手续费，但应该只设置一次
            if len(cells) > 4:
                item["fee"] = float(cells[4])

            # 添加到交易记录列表
            items.append(item)
        
        return items

    def get_bt_rounds(self, path:str, straid:str) -> list:
        """
        获取回测交易回合数据
        
        读取回测的交易回合CSV文件，解析为字典列表。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 交易回合数据列表，每个元素包含合约代码、方向、开仓时间、开仓价、平仓时间、平仓价等信息
        """
        # 构建交易回合CSV文件路径
        filename = f"{straid}/closes.csv"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建交易回合列表
        items = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建交易回合项
            item = {
                "code": cells[0],  # 合约代码
                "direct": cells[1],  # 交易方向（多/空）
                "opentime": int(cells[2]),  # 开仓时间
                "openprice": float(cells[3]),  # 开仓价格
                "closetime": int(cells[4]),  # 平仓时间
                "closeprice": float(cells[5]),  # 平仓价格
                "qty": float(cells[6]),  # 交易数量
                "profit": float(cells[7]),  # 盈亏
                "maxprofit": float(cells[8]),  # 最大盈利
                "maxloss": float(cells[9]),  # 最大亏损
                "entertag": cells[11],  # 进场标记
                "exittag": cells[12]  # 出场标记
            }

            # 添加到交易回合列表
            items.append(item)
        
        return items

    def get_bt_signals(self, path:str, straid:str) -> list:
        """
        获取回测信号数据
        
        读取回测的信号CSV文件，解析为字典列表。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 信号数据列表，每个元素包含合约代码、目标价格、信号价格、生成时间、标记等信息
        """
        # 构建信号CSV文件路径
        filename = f"{straid}/signals.csv"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取文件内容
        f = open(filename, "r")
        lines = f.readlines()
        f.close()
        # 跳过第一行（表头）
        lines = lines[1:]

        # 创建信号列表
        items = list()
        # 遍历所有行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建信号项
            item = {
                "code": cells[0],  # 合约代码
                "target": float(cells[1]),  # 目标价格
                "sigprice": float(cells[2]),  # 信号价格
                "gentime": cells[3],  # 生成时间
                "tag": cells[4]  # 用户标记
            }

            # 添加到信号列表
            items.append(item)
        
        return items

    def get_bt_kline(self, path:str, straid:str) -> list:
        """
        获取回测K线数据
        
        从数据服务器获取回测使用的K线数据，并加载指标数据和标记数据。
        
        @param path: 工作空间路径（字符串），回测结果文件的路径
        @param straid: 策略ID（字符串），策略标识
        @return: 元组，包含合约代码、K线数据列表、指标数据、标记数据
        """
        # 如果数据服务器未设置，返回None
        if self.dt_servo is None:
            return None

        # 构建环境JSON文件路径
        filename = f"{straid}/btenv.json"
        filename = os.path.join(path, filename)
        # 如果文件不存在，返回None
        if not os.path.exists(filename):
            return None

        # 读取环境文件内容
        f = open(filename, "r")
        content = f.read()
        f.close()

        # 解析JSON内容
        btState = json.loads(content)

        # 从环境信息中获取K线参数
        code = btState["code"]  # 合约代码
        period = btState["period"]  # K线周期
        stime = btState["stime"]  # 开始时间
        etime = btState["etime"]  # 结束时间

        # 初始化指标数据和标记数据
        index = None
        marks = None

        # ========== 加载图表配置（如果有） ==========
        # 如果有btchart配置文件，使用btchart定义的K线参数
        filename = f"{straid}/btchart.json"
        filename = os.path.join(path, filename)
        if os.path.exists(filename):
            # 读取图表配置文件内容
            f = open(filename, "r")
            content = f.read()
            f.close()

            # 解析JSON内容
            btchart = json.loads(content)
            # 使用图表配置中的K线参数
            code = btchart['kline']["code"]  # 合约代码
            period = btchart['kline']["period"]  # K线周期

            # 如果包含指标数据，加载指标数据
            if "index" in btchart:
                index = btchart["index"]

        # ========== 加载标记数据 ==========
        # 构建标记CSV文件路径
        filename = f"{straid}/marks.csv"
        filename = os.path.join(path, filename)
        if os.path.exists(filename):
            # 读取标记文件内容
            f = open(filename, "r")
            lines = f.readlines()
            f.close()

            # 如果行数大于2（包含表头和至少一条数据），解析标记数据
            if len(lines) > 2:
                marks = []
                # 遍历所有数据行（跳过第一行表头和最后一行空行）
                for line in lines[1:-1]:
                    # 按逗号分割单元格
                    items = line.split(",")
                    # 创建标记项
                    marks.append({
                        "bartime": int(items[0]),  # K线时间
                        "price": float(items[1]),  # 标记价格
                        "icon": items[2],  # 图标ID
                        "tag": items[3]  # 标记标签
                    })

        # ========== 加载指标数据 ==========
        # 构建指标CSV文件路径
        filename = f"{straid}/indice.csv"
        filename = os.path.join(path, filename)
        if os.path.exists(filename):
            # 读取指标文件内容
            f = open(filename, "r")
            lines = f.readlines()
            f.close()

            # 如果行数大于2（包含表头和至少一条数据），解析指标数据
            if len(lines) > 2:
                # 遍历所有数据行（跳过第一行表头和最后一行空行）
                for line in lines[1:-1]:
                    # 按逗号分割单元格
                    items = line.split(",")
                    index_name = items[1]  # 指标名称
                    line_name = items[2]  # 线名称
                    index_val = float(items[3])  # 指标值
                    # 在指标数据中查找对应的指标
                    for iInfo in index:
                        # 如果指标名称不匹配，继续查找下一个指标
                        if iInfo["name"] != index_name:
                            continue

                        # 在指标的所有线中查找对应的线
                        for lInfo in iInfo["lines"]:
                            # 如果线名称不匹配，继续查找下一条线
                            if lInfo["name"] != line_name:
                                continue

                            # 如果线数据中没有values字段，创建values列表
                            if "values" not in lInfo:
                                lInfo["values"] = list()

                            # 将指标值添加到线的values列表中
                            lInfo["values"].append(index_val)

        # ========== 从数据服务器获取K线数据 ==========
        # 从数据服务器获取K线数据
        barList = self.dt_servo.get_bars(stdCode=code, period=period, fromTime=stime, endTime=etime)
        # 如果获取失败，返回None
        if barList is None:
            return None

        # 判断是否为日线周期（日线周期以'd'开头）
        isDay = period[0]=='d'

        # 创建K线数据列表
        bars = list()
        # 遍历所有K线，转换为字典格式
        for realBar in barList:
            bar = dict()
            # 设置K线时间：日线使用date，其他周期使用bartime（加上1990年作为基准年份）
            bar["bartime"] = int(realBar.date if isDay  else 199000000000 + realBar.bartime)
            bar["open"] = realBar.open  # 开盘价
            bar["high"] = realBar.high  # 最高价
            bar["low"] = realBar.low  # 最低价
            bar["close"] = realBar.close  # 收盘价
            bar["volume"] = realBar.volume  # 成交量
            bar["turnover"] = realBar.money  # 成交额
            bars.append(bar)

        # 返回K线数据、指标数据和标记数据
        return code, bars, index, marks
