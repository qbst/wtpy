"""
WonderTrader数据管理模块

该模块提供了监控系统的数据管理功能，使用SQLite数据库存储组合、用户、调度等配置信息。
支持组合管理、用户管理、调度管理等功能。

主要功能：
1. 数据库管理：创建和管理SQLite数据库，包括表结构创建和索引管理
2. 组合管理：管理交易组合（group）的配置信息
3. 用户管理：管理用户信息、权限、产品访问权限等
4. 调度管理：管理应用的调度配置
5. 缓存管理：缓存组合的策略、通道、执行器等信息，提高查询性能
6. 配置文件管理：读取和管理组合的配置文件（JSON/YAML）

设计模式：
- 使用SQLite数据库进行数据持久化
- 使用缓存机制提高查询性能（60秒缓存过期）
- 使用单例模式管理数据库连接
"""

import json
import yaml
import os
import sqlite3
import hashlib
import datetime
from .WtLogger import WtLogger

def backup_file(filename):
    """
    备份文件函数
    
    将文件备份为带时间戳的新文件，格式为：原文件名_YYYYMMDD_HHMMSS.扩展名
    
    @param filename: 要备份的文件路径（字符串）
    """
    # 如果文件不存在，直接返回
    if not os.path.exists(filename):
        return

    # 分割文件名和扩展名
    items = filename.split(".")
    ext = items[-1]  # 扩展名
    prefix = ".".join(items[:-1])  # 文件名前缀（不含扩展名）

    # 获取当前时间并格式化为时间戳
    now = datetime.datetime.now()
    timetag = now.strftime("%Y%m%d_%H%M%S")
    # 构建备份文件名
    target = prefix + "_" + timetag + "." + ext
    # 复制文件到备份位置
    import shutil
    shutil.copy(filename, target)

class DataMgr:
    """
    数据管理器类
    
    管理监控系统的所有数据，包括组合、用户、调度等配置信息。
    使用SQLite数据库进行数据持久化，并提供缓存机制提高查询性能。
    
    主要功能：
    1. 数据库管理：创建和管理SQLite数据库表结构
    2. 组合管理：管理交易组合的配置信息
    3. 用户管理：管理用户信息和权限
    4. 调度管理：管理应用的调度配置
    5. 缓存管理：缓存组合的策略、通道、执行器等信息
    """

    def __init__(self, datafile:str="mondata.db", logger:WtLogger=None):
        """
        初始化数据管理器
        
        创建数据库连接，检查并创建表结构，加载组合和用户配置。
        
        @param datafile: 数据库文件路径（字符串，默认"mondata.db"），SQLite数据库文件路径
        @param logger: 日志记录器（WtLogger，默认None），用于记录日志
        """
        # 组合缓存字典，key为组合ID，value为缓存数据（策略、通道、执行器等）
        self.__grp_cache__ = dict()
        # 日志记录器引用
        self.__logger__ = logger

        # 创建SQLite数据库连接（check_same_thread=False允许多线程访问）
        self.__db_conn__ = sqlite3.connect(datafile, check_same_thread=False)
        # 检查并创建数据库表结构
        self.__check_db__()

        # ========== 加载组合列表 ==========
        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 初始化配置字典
        self.__config__ = {
            "groups":{},  # 组合字典，key为组合ID，value为组合信息
            "users":{}  # 用户字典，key为登录ID，value为用户信息
        }

        # 查询所有组合配置
        for row in cur.execute("SELECT * FROM groups;"):
            # 创建组合信息字典
            grpInfo = dict()
            grpInfo["id"] = row[1]  # 组合ID（第2列，索引1）
            grpInfo["name"] = row[2]  # 组合名称（第3列，索引2）
            grpInfo["path"] = row[3]  # 组合路径（第4列，索引3）
            grpInfo["info"] = row[4]  # 组合信息（第5列，索引4）
            grpInfo["gtype"] = row[5]  # 组合类型（第6列，索引5），如cta、hft、sel等
            grpInfo["datmod"] = row[6]  # 数据模式（第7列，索引6），如mannual（手动）、auto（自动）等
            grpInfo["env"] = row[7]  # 环境（第8列，索引7），如product（生产）、sim（模拟）等
            grpInfo["mqurl"] = row[8]  # 消息队列URL（第9列，索引8）
            # 将组合信息添加到配置字典
            self.__config__["groups"][grpInfo["id"]] = grpInfo

        # ========== 加载用户列表 ==========
        # 查询所有用户配置
        for row in cur.execute("SELECT id,loginid,name,role,passwd,iplist,remark,createby,createtime,modifyby,modifytime,products FROM users;"):
            # 创建用户信息字典
            usrInfo = dict()
            usrInfo["loginid"] = row[1]  # 登录ID（第2列，索引1）
            usrInfo["name"] = row[2]  # 用户名称（第3列，索引2）
            usrInfo["role"] = row[3]  # 用户角色（第4列，索引3），如admin、user等
            usrInfo["passwd"] = row[4]  # 密码（第5列，索引4）
            usrInfo["iplist"] = row[5]  # IP白名单（第6列，索引5），逗号分隔的IP列表
            usrInfo["remark"] = row[6]  # 备注（第7列，索引6）
            usrInfo["createby"] = row[7]  # 创建者（第8列，索引7）
            usrInfo["createtime"] = row[8]  # 创建时间（第9列，索引8）
            usrInfo["modifyby"] = row[9]  # 修改者（第10列，索引9）
            usrInfo["modifytime"] = row[10]  # 修改时间（第11列，索引10）
            # 解析产品列表（逗号分隔的字符串）
            products = row[11]  # 产品列表（第12列，索引11）
            if len(products) != 0:
                products = products.split(',')  # 按逗号分割
            else:
                products = []  # 如果为空，设置为空列表
            usrInfo["products"] = products
            # 将用户信息添加到配置字典
            self.__config__["users"][usrInfo["loginid"]] = usrInfo

    def get_db(self):
        """
        获取数据库连接
        
        返回SQLite数据库连接对象。
        
        @return: SQLite数据库连接对象
        """
        return self.__db_conn__

    def __check_db__(self):
        """
        检查并创建数据库表结构（私有方法）
        
        检查数据库中的表是否存在，如果不存在则创建相应的表。
        包括actions（操作日志）、groups（组合）、schedules（调度）、users（用户）四个表。
        """
        # 如果数据库连接为空，直接返回
        if self.__db_conn__ is None:
            return

        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 查询所有表名
        tables = []
        for row in cur.execute("select name from sqlite_master where type='table' order by name"):
            tables.append(row[0])
        
        # ========== 创建actions表（操作日志表） ==========
        if "actions" not in tables:
            # 构建创建表的SQL语句
            sql = "CREATE TABLE [actions] (\n"
            sql += "[id] INTEGER PRIMARY KEY autoincrement, \n"  # 主键ID，自增
            sql += "[loginid] VARCHAR(20) NOT NULL DEFAULT '', \n"  # 登录ID
            sql += "[actiontime] DATETIME default (datetime('now', 'localtime')), \n"  # 操作时间，默认为当前时间
            sql += "[actionip] VARCHAR(30) NOT NULL DEFAULT '', \n"  # 操作IP地址
            sql += "[actiontype] VARCHAR(20) NOT NULL DEFAULT '',\n"  # 操作类型
            sql += "[remark] TEXT default '');"  # 备注信息
            # 执行SQL语句创建表
            cur.execute(sql)
            # 创建登录ID索引，提高查询性能
            cur.execute("CREATE INDEX [idx_actions_loginid] ON [actions] ([loginid]);")
            # 创建操作时间索引，提高查询性能
            cur.execute("CREATE INDEX [idx_actions_actiontime] ON [actions] ([actiontime]);")
            # 提交事务
            self.__db_conn__.commit()

        # ========== 创建groups表（组合表） ==========
        if "groups" not in tables:
            # 构建创建表的SQL语句
            sql = "CREATE TABLE [groups] (\n"
            sql += "[id] INTEGER PRIMARY KEY autoincrement,\n"  # 主键ID，自增
            sql += "[groupid] VARCHAR(20) NOT NULL DEFAULT '',\n"  # 组合ID
            sql += "[name] VARCHAR(30) NOT NULL DEFAULT '',\n"  # 组合名称
            sql += "[path] VARCHAR(256) NOT NULL DEFAULT '',\n"  # 组合路径
            sql += "[info] TEXT DEFAULT '',\n"  # 组合信息
            sql += "[gtype] VARCHAR(10) NOT NULL DEFAULT 'cta',\n"  # 组合类型，默认为cta
            sql += "[datmod] VARCHAR(10) NOT NULL DEFAULT 'mannual',\n"  # 数据模式，默认为mannual（手动）
            sql += "[env] VARCHAR(20) NOT NULL DEFAULT 'product',\n"  # 环境，默认为product（生产）
            sql += "[mqurl] VARCHAR(255) NOT NULL DEFAULT '',\n"  # 消息队列URL
            sql += "[createtime] DATETIME default (datetime('now', 'localtime')),\n"  # 创建时间，默认为当前时间
            sql += "[modifytime] DATETIME default (datetime('now', 'localtime')));"  # 修改时间，默认为当前时间
            # 执行SQL语句创建表
            cur.execute(sql)
            # 创建组合ID唯一索引，确保组合ID唯一
            cur.execute("CREATE UNIQUE INDEX [idx_groupid] ON [groups] ([groupid]);")
            # 提交事务
            self.__db_conn__.commit()

        # ========== 创建schedules表（调度表） ==========
        if "schedules" not in tables:
            # 构建创建表的SQL语句
            sql = "CREATE TABLE [schedules] (\n"
            sql += "[id] INTEGER PRIMARY KEY autoincrement,\n"  # 主键ID，自增
            sql += "[appid] VARCHAR(20) NOT NULL DEFAULT '',\n"  # 应用ID
            sql += "[path] VARCHAR(256) NOT NULL DEFAULT '',\n"  # 应用路径
            sql += "[folder] VARCHAR(256) NOT NULL DEFAULT '',\n"  # 工作目录
            sql += "[param] VARCHAR(50) NOT NULL DEFAULT '',\n"  # 应用参数
            sql += "[type] INTEGER DEFAULT 0,\n"  # 应用类型，0表示普通应用，1表示分组应用
            sql += "[span] INTEGER DEFAULT 3,\n"  # 检查间隔（秒），默认为3秒
            sql += "[guard] VARCHAR(20) DEFAULT 'false',\n"  # 守护标志，默认为false（不守护）
            sql += "[redirect] VARCHAR(20) DEFAULT 'false',\n"  # 重定向标志，默认为false（不重定向输出）
            sql += "[schedule] VARCHAR(20) DEFAULT 'false',\n"  # 调度激活标志，默认为false（不启用调度）
            sql += "[weekflag] VARCHAR(20) DEFAULT '000000',\n"  # 周标志字符串，7位字符串，每位表示一周中的某一天是否启用调度
            sql += "[mqurl] VARCHAR(255) NOT NULL DEFAULT '',\n"  # 消息队列URL
            sql += "[task1] VARCHAR(100) NOT NULL DEFAULT '{\"active\": true,\"time\": 0,\"action\": 0}',\n"  # 调度任务1（JSON字符串）
            sql += "[task2] VARCHAR(100) NOT NULL DEFAULT '{\"active\": true,\"time\": 0,\"action\": 0}',\n"  # 调度任务2（JSON字符串）
            sql += "[task3] VARCHAR(100) NOT NULL DEFAULT '{\"active\": true,\"time\": 0,\"action\": 0}',\n"  # 调度任务3（JSON字符串）
            sql += "[task4] VARCHAR(100) NOT NULL DEFAULT '{\"active\": true,\"time\": 0,\"action\": 0}',\n"  # 调度任务4（JSON字符串）
            sql += "[task5] VARCHAR(100) NOT NULL DEFAULT '{\"active\": true,\"time\": 0,\"action\": 0}',\n"  # 调度任务5（JSON字符串）
            sql += "[task6] VARCHAR(100) NOT NULL DEFAULT '{\"active\": true,\"time\": 0,\"action\": 0}',\n"  # 调度任务6（JSON字符串）
            sql += "[createtime] DATETIME default (datetime('now', 'localtime')),\n"  # 创建时间，默认为当前时间
            sql += "[modifytime] DATETIME default (datetime('now', 'localtime')));"  # 修改时间，默认为当前时间
            # 执行SQL语句创建表
            cur.execute(sql)
            # 创建应用ID唯一索引，确保应用ID唯一
            cur.execute("CREATE UNIQUE INDEX [idx_appid] ON [schedules] ([appid]);")
            # 提交事务
            self.__db_conn__.commit()

        # ========== 创建users表（用户表） ==========
        if "users" not in tables:
            # 构建创建表的SQL语句
            sql = "CREATE TABLE [users] (\n"
            sql += "[id] INTEGER PRIMARY KEY autoincrement,\n"  # 主键ID，自增
            sql += "[loginid] VARCHAR(20) NOT NULL DEFAULT '',\n"  # 登录ID
            sql += "[name] VARCHAR(30) NOT NULL DEFAULT '',\n"  # 用户名称
            sql += "[role] VARCHAR(10) NOT NULL DEFAULT '',\n"  # 用户角色
            sql += "[passwd] VARCHAR(30) NOT NULL DEFAULT 'cta',\n"  # 密码，默认为'cta'
            sql += "[iplist] VARCHAR(100) NOT NULL DEFAULT 'mannual',\n"  # IP白名单，默认为'mannual'
            sql += "[products] VARCHAR(256) NOT NULL DEFAULT 'mannual',\n"  # 产品列表，默认为'mannual'
            sql += "[remark] VARCHAR(256) NOT NULL DEFAULT '',\n"  # 备注信息
            sql += "[createby] VARCHAR(20) NOT NULL DEFAULT '',\n"  # 创建者
            sql += "[createtime] DATETIME default (datetime('now', 'localtime')),\n"  # 创建时间，默认为当前时间
            sql += "[modifyby] VARCHAR(20) NOT NULL DEFAULT '',\n"  # 修改者
            sql += "[modifytime] DATETIME default (datetime('now', 'localtime')));"  # 修改时间，默认为当前时间
            # 执行SQL语句创建表
            cur.execute(sql)
            # 创建登录ID唯一索引，确保登录ID唯一
            cur.execute("CREATE UNIQUE INDEX [idx_loginid] ON [users] ([loginid]);")
            # 提交事务
            self.__db_conn__.commit()

    def __check_cache__(self, grpid, grpInfo):
        """
        检查并更新组合缓存（私有方法）
        
        检查组合缓存是否存在或过期，如果不存在或过期（超过60秒），则重新加载缓存。
        缓存包含策略列表、通道列表、执行器列表等信息。
        
        @param grpid: 组合ID（字符串），要检查的组合标识
        @param grpInfo: 组合信息字典，包含组合的路径等信息
        """
        # 获取当前时间
        now = datetime.datetime.now()
        # 如果组合缓存不存在，初始化缓存字典
        if grpid not in self.__grp_cache__:
            self.__grp_cache__[grpid] = dict()
            self.__grp_cache__[grpid]["cachetime"] = None
        else:
            # 如果组合缓存存在，检查是否过期
            cache_time = self.__grp_cache__[grpid]["cachetime"]
            bNeedReset = False
            # 如果缓存时间为空或缓存中没有策略信息，需要重置
            if cache_time is None or "strategies" not in self.__grp_cache__[grpid]:
                bNeedReset = True
            else:
                # 计算时间差
                td = now - cache_time
                # 如果上次缓存时间超过60秒，则重新读取
                if td.total_seconds() >= 60:
                    bNeedReset = True

            # 如果需要重置，清空缓存
            if bNeedReset:
                self.__grp_cache__[grpid] = dict()
                self.__grp_cache__[grpid]["cachetime"] = None

        # 如果缓存中没有策略信息，从文件加载
        if "strategies" not in self.__grp_cache__[grpid]:
            # 构建标记文件路径（marker.json存储策略、通道、执行器列表）
            filepath = "./generated/marker.json"
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，跳过
            if not os.path.exists(filepath):
                pass
            else:
                try:
                    # 读取标记文件内容
                    f = open(filepath, "r")
                    content = f.read()
                    marker = json.loads(content)
                    f.close()

                    # 更新缓存，包含策略列表和通道列表
                    self.__grp_cache__[grpid] = {
                        "strategies":marker["marks"],  # 策略列表
                        "channels":marker["channels"]  # 通道列表
                    } 

                    # 如果标记文件包含执行器列表，添加到缓存
                    if "executers" in marker:
                        self.__grp_cache__[grpid]["executers"] = marker["executers"]
                    else:
                        # 否则设置为空列表
                        self.__grp_cache__[grpid]["executers"] = []

                except:
                    # 如果读取失败，设置为空列表
                    self.__grp_cache__[grpid] = {
                        "strategies":[],  # 策略列表为空
                        "channels":[],  # 通道列表为空
                        "executers":[]  # 执行器列表为空
                    } 

            # 对策略列表进行排序
            if "strategies" in self.__grp_cache__[grpid]:
                self.__grp_cache__[grpid]["strategies"].sort()

            # 对通道列表进行排序
            if "channels" in self.__grp_cache__[grpid]:
                self.__grp_cache__[grpid]["channels"].sort()

            # 对执行器列表进行排序
            if "executers" in self.__grp_cache__[grpid]:
                self.__grp_cache__[grpid]["executers"].sort()

            # 更新缓存时间
            self.__grp_cache__[grpid]["cachetime"] = now

    def get_groups(self, tpfilter:str=''):
        """
        获取组合列表
        
        返回所有组合的列表，可以按类型过滤。
        
        @param tpfilter: 类型过滤器（字符串，默认空字符串），如果为空则返回所有组合，否则只返回指定类型的组合
        @return: 组合信息列表
        """
        # 创建返回列表
        ret = []
        # 遍历所有组合
        for grpid in self.__config__["groups"]:
            grpinfo = self.__config__["groups"][grpid]
            # 如果过滤器为空，添加所有组合
            if tpfilter == '':
                ret.append(grpinfo)
            # 如果组合类型匹配过滤器，添加该组合
            elif grpinfo["gtype"] == tpfilter:
                ret.append(grpinfo)
        
        return ret

    def has_group(self, grpid:str):
        """
        检查组合是否存在
        
        @param grpid: 组合ID（字符串），要检查的组合标识
        @return: 如果组合存在返回True，否则返回False
        """
        return (grpid in self.__config__["groups"])

    def get_group(self, grpid:str) -> dict:
        """
        获取组合信息
        
        @param grpid: 组合ID（字符串），要获取的组合标识
        @return: 组合信息字典，如果组合不存在则返回None
        """
        if grpid in self.__config__["groups"]:
            return self.__config__["groups"][grpid]
        else:
            return None

    def get_group_cfg(self, grpid:str):
        """
        获取组合配置文件内容
        
        读取组合的配置文件（config.json或config.yaml），返回配置内容字符串。
        
        @param grpid: 组合ID（字符串），要获取配置的组合标识
        @return: 配置文件内容（字符串），如果组合不存在或文件不存在则返回"{}"
        """
        # 如果组合不存在，返回空JSON对象
        if grpid not in self.__config__["groups"]:
            return "{}"
        else:
            # 获取组合信息
            grpInfo = self.__config__["groups"][grpid]
            # 先尝试读取config.json文件
            filepath = "./config.json"
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果config.json不存在，尝试读取config.yaml文件
            if not os.path.exists(filepath):
                filepath = "./config.yaml"
                filepath = os.path.join(grpInfo["path"], filepath)

            # 读取配置文件内容
            f = open(filepath, "r")
            content = f.read()
            f.close()
            # 如果是YAML文件，需要转换为JSON格式
            if filepath.lower()[-4:] == 'yaml':
                # 使用yaml.full_load解析YAML内容为Python对象
                return yaml.full_load(content)
            else:
                # 使用json.loads解析JSON内容为Python对象
                return json.loads(content)

    def set_group_cfg(self, grpid:str, config:dict):
        """
        设置组合配置文件内容
        
        将配置字典写入组合的配置文件（config.json或config.yaml）。
        写入前会先备份原文件。
        
        @param grpid: 组合ID（字符串），要设置配置的组合标识
        @param config: 配置字典，要写入的配置内容
        @return: 如果设置成功返回True，否则返回False
        """
        # 如果组合不存在，返回False
        if grpid not in self.__config__["groups"]:
            return False
        else:
            # 获取组合信息
            grpInfo = self.__config__["groups"][grpid]
            # 先尝试读取config.json文件
            filepath = "./config.json"
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果config.json不存在，尝试读取config.yaml文件
            if not os.path.exists(filepath):
                filepath = "./config.yaml"
                filepath = os.path.join(grpInfo["path"], filepath)
            # 备份原文件
            backup_file(filepath)
            # 打开文件并写入配置
            f = open(filepath, "w")
            # 如果是YAML文件，使用yaml.dump写入
            if filepath.lower()[-4:] == 'yaml':
                yaml.dump(config, f, indent=4, allow_unicode=True)
            else:
                # 否则使用json.dumps写入JSON格式
                f.write(json.dumps(config, indent=4))
            f.close()
            return True

    def get_group_entry(self, grpid:str):
        """
        获取组合入口文件内容
        
        读取组合的入口文件（run.py）内容。
        
        @param grpid: 组合ID（字符串），要获取入口文件的组合标识
        @return: 入口文件内容（字符串），如果组合不存在或文件不存在则返回"{}"
        """
        # 如果组合不存在，返回空JSON对象
        if grpid not in self.__config__["groups"]:
            return "{}"
        else:
            # 获取组合信息
            grpInfo = self.__config__["groups"][grpid]
            # 构建入口文件路径
            filepath = "./run.py"
            filepath = os.path.join(grpInfo["path"], filepath)
            # 读取文件内容（使用UTF-8编码）
            f = open(filepath, "r", encoding="utf-8")
            content = f.read()
            f.close()
            return content

    def set_group_entry(self, grpid:str, content:str):
        """
        设置组合入口文件内容
        
        将内容写入组合的入口文件（run.py）。
        写入前会先备份原文件。
        
        @param grpid: 组合ID（字符串），要设置入口文件的组合标识
        @param content: 文件内容（字符串），要写入的内容
        @return: 如果设置成功返回True，否则返回False
        """
        # 如果组合不存在，返回False
        if grpid not in self.__config__["groups"]:
            return False
        else:
            # 获取组合信息
            grpInfo = self.__config__["groups"][grpid]
            # 构建入口文件路径
            filepath = "./run.py"
            filepath = os.path.join(grpInfo["path"], filepath)
            # 备份原文件
            backup_file(filepath)
            # 打开文件并写入内容（使用UTF-8编码）
            f = open(filepath, "w", encoding="utf-8")
            f.write(content)
            f.close()
            return True

    def add_group(self, grpInfo:dict):
        """
        添加或更新组合
        
        将组合信息添加到数据库和内存配置中。
        如果组合已存在，则更新；否则插入新记录。
        
        @param grpInfo: 组合信息字典，包含组合的ID、名称、路径等信息
        @return: 如果操作成功返回True，否则返回False
        """
        # 获取组合ID
        grpid = grpInfo["id"]
        # 判断是否为新组合
        isNewGrp = not (grpid in self.__config__["groups"])

        bSucc = False
        try:
            # 获取数据库游标
            cur = self.__db_conn__.cursor()
            sql = ''
            # 如果是新组合，执行INSERT语句
            if isNewGrp:
                sql = "INSERT INTO groups(groupid,name,path,info,gtype,datmod,env,mqurl) VALUES('%s','%s','%s','%s','%s','%s','%s','%s');" \
                    % (grpid, grpInfo["name"], grpInfo["path"], grpInfo["info"], grpInfo["gtype"], grpInfo["datmod"], grpInfo["env"], grpInfo["mqurl"])
            else:
                # 如果是现有组合，执行UPDATE语句
                sql = "UPDATE groups SET name='%s',path='%s',info='%s',gtype='%s',datmod='%s',env='%s',mqurl='%s',modifytime=datetime('now','localtime') WHERE groupid='%s';" \
                    % (grpInfo["name"], grpInfo["path"], grpInfo["info"], grpInfo["gtype"], grpInfo["datmod"], grpInfo["env"], grpInfo["mqurl"], grpid)
            # 执行SQL语句
            cur.execute(sql)
            # 提交事务
            self.__db_conn__.commit()
            bSucc = True
        except sqlite3.Error as e:
            # 如果发生数据库错误，打印错误信息
            print(e)

        # 如果操作成功，更新内存配置
        if bSucc:
            self.__config__["groups"][grpid] = grpInfo

        return bSucc

    def del_group(self, grpid:str):
        """
        删除组合
        
        从数据库和内存配置中删除指定组合。
        
        @param grpid: 组合ID（字符串），要删除的组合标识
        """
        # 如果组合存在，执行删除操作
        if grpid in self.__config__["groups"]:
            # 从内存配置中删除组合
            self.__config__["groups"].pop(grpid)
            
            # 获取数据库游标
            cur = self.__db_conn__.cursor()
            # 从数据库中删除组合
            cur.execute("DELETE FROM groups WHERE groupid='%s';" % (grpid))
            # 提交事务
            self.__db_conn__.commit()

    def get_users(self):
        """
        获取所有用户列表
        
        返回所有用户的列表，每个用户信息都是副本，避免外部修改影响内部状态。
        
        @return: 用户信息列表
        """
        # 创建返回列表
        ret = []
        # 遍历所有用户
        for loginid in self.__config__["users"]:
            usrInfo = self.__config__["users"][loginid]
            # 添加用户信息的副本
            ret.append(usrInfo.copy())                
        
        return ret

    def add_user(self, usrInfo, admin):
        """
        添加或更新用户
        
        将用户信息添加到数据库和内存配置中。
        如果用户已存在，则更新；否则插入新记录。
        新用户的密码会使用MD5加密（loginid+passwd）。
        
        @param usrInfo: 用户信息字典，包含登录ID、名称、角色、密码等信息
        @param admin: 管理员登录ID（字符串），执行操作的管理员
        """
        # 获取登录ID
        loginid = usrInfo["loginid"]
        # 判断是否为新用户
        isNewUser = not (loginid in self.__config__["users"])

        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 获取当前时间
        now = datetime.datetime.now()
        # 如果是新用户，执行INSERT语句
        if isNewUser:
            # 使用MD5加密密码（loginid+passwd）
            encpwd = hashlib.md5((loginid+usrInfo["passwd"]).encode("utf-8")).hexdigest()
            # 更新用户信息中的密码
            usrInfo["passwd"] = encpwd
            # 设置创建者和修改者
            usrInfo["createby"] = admin
            usrInfo["modifyby"] = admin
            # 设置创建时间和修改时间
            usrInfo["createtime"] = now.strftime("%Y-%m-%d %H:%M:%S")
            usrInfo["modifytime"] = now.strftime("%Y-%m-%d %H:%M:%S")
            # 执行INSERT语句（使用参数化查询，避免SQL注入）
            cur.execute("INSERT INTO users(loginid,name,role,passwd,iplist,products,remark,createby,modifyby) VALUES(?,?,?,?,?,?,?,?,?);", 
                (loginid, usrInfo["name"], usrInfo["role"], encpwd, usrInfo["iplist"], usrInfo["products"], usrInfo["remark"], admin, admin))
        else:
            # 如果是现有用户，执行UPDATE语句
            usrInfo["modifyby"] = admin
            usrInfo["modifytime"] = now.strftime("%Y-%m-%d %H:%M:%S")
            # 执行UPDATE语句（使用参数化查询，避免SQL注入）
            cur.execute("UPDATE users SET name=?,role=?,iplist=?,products=?,remark=?,modifyby=?,modifytime=datetime('now','localtime') WHERE loginid=?;", 
                (usrInfo["name"], usrInfo["role"], usrInfo["iplist"], usrInfo["products"], usrInfo["remark"], admin, loginid))
        # 提交事务
        self.__db_conn__.commit()

        # 如果用户已存在于内存配置中，更新修改者和修改时间
        if loginid in self.__config__["users"]:
            self.__config__["users"][loginid]["modifyby"] = admin
            self.__config__["users"][loginid]["modifytime"] = usrInfo["modifytime"]

    def mod_user_pwd(self, loginid:str, newpwd:str, admin:str):
        """
        修改用户密码
        
        更新指定用户的密码。
        
        @param loginid: 登录ID（字符串），要修改密码的用户标识
        @param newpwd: 新密码（字符串），已加密的密码（MD5哈希值）
        @param admin: 管理员登录ID（字符串），执行操作的管理员
        """
        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 执行UPDATE语句更新密码（使用参数化查询，避免SQL注入）
        cur.execute("UPDATE users SET passwd=?,modifyby=?,modifytime=datetime('now','localtime') WHERE loginid=?;", 
                (newpwd,admin,loginid))
        # 提交事务
        self.__db_conn__.commit()
        # 更新内存配置中的密码
        self.__config__["users"][loginid]["passwd"]=newpwd


    def del_user(self, loginid, admin):
        """
        删除用户
        
        从数据库和内存配置中删除指定用户。
        
        @param loginid: 登录ID（字符串），要删除的用户标识
        @param admin: 管理员登录ID（字符串），执行操作的管理员（当前未使用）
        @return: 如果删除成功返回True，否则返回False
        """
        # 如果用户存在，执行删除操作
        if loginid in self.__config__["users"]:
            # 从内存配置中删除用户
            self.__config__["users"].pop(loginid)
            
            # 获取数据库游标
            cur = self.__db_conn__.cursor()
            # 从数据库中删除用户
            cur.execute("DELETE FROM users WHERE loginid='%s';" % (loginid))
            # 提交事务
            self.__db_conn__.commit()
            return True
        else:
            return False

    def log_action(self, adminInfo, atype, remark):
        """
        记录操作日志
        
        将管理员的操作记录到actions表中。
        
        @param adminInfo: 管理员信息字典，包含loginid和loginip字段
        @param atype: 操作类型（字符串），如"login"、"logout"、"add_user"等
        @param remark: 备注信息（字符串），操作的详细说明
        """
        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 构建INSERT语句
        sql = "INSERT INTO actions(loginid,actiontime,actionip,actiontype,remark) VALUES('%s',datetime('now','localtime'),'%s','%s','%s');" % (
                adminInfo["loginid"], adminInfo["loginip"], atype, remark)
        # 执行SQL语句
        cur.execute(sql)
        # 提交事务
        self.__db_conn__.commit()

    def get_user(self, loginid:str):
        """
        获取用户信息
        
        根据登录ID获取用户信息。
        如果登录ID为'superman'，返回内置超管账号信息。
        
        @param loginid: 登录ID（字符串），要查询的用户标识
        @return: 用户信息字典，如果用户不存在则返回None
        """
        # 如果用户存在于内存配置中，返回用户信息的副本
        if loginid in self.__config__["users"]:
            return self.__config__["users"][loginid].copy()
        # 如果是内置超管账号，返回超管信息
        elif loginid == 'superman':
            return {
                "loginid":loginid,  # 登录ID
                "name":"超管",  # 用户名称
                "role":"superman",  # 用户角色
                "passwd":"25ed305a56504e95fd1ca9900a1da174",  # 密码（MD5哈希值，原始密码为"superman"）
                "iplist":"",  # IP白名单（空表示不限制）
                "remark":"内置超管账号",  # 备注信息
                'builtin':True,  # 内置账号标志
                'products':''  # 产品列表（空表示可访问所有产品）
            }
        else:
            return None

    def get_strategies(self, grpid:str):
        """
        获取组合的策略列表
        
        返回指定组合的所有策略名称列表。
        会先检查并更新缓存。
        
        @param grpid: 组合ID（字符串），要查询策略的组合标识
        @return: 策略名称列表，如果组合不存在或没有策略则返回空列表
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有策略信息，返回空列表
        if "strategies" not in self.__grp_cache__[grpid]:
            return []
        
        # 返回策略列表
        return self.__grp_cache__[grpid]["strategies"]

    def get_channels(self, grpid:str):
        """
        获取组合的通道列表
        
        返回指定组合的所有通道名称列表。
        会先检查并更新缓存。
        
        @param grpid: 组合ID（字符串），要查询通道的组合标识
        @return: 通道名称列表，如果组合不存在或没有通道则返回空列表
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)
        
        # 如果缓存中没有通道信息，返回空列表
        if "channels" not in self.__grp_cache__[grpid]:
            return []

        # 返回通道列表
        return self.__grp_cache__[grpid]["channels"]

    def get_trades(self, grpid:str, straid:str, limit:int = 200):
        """
        获取策略的交易记录
        
        读取指定策略的交易记录CSV文件，解析为字典列表。
        使用增量读取机制，只读取新增的交易记录。
        
        @param grpid: 组合ID（字符串），策略所属的组合标识
        @param straid: 策略ID（字符串），要查询交易记录的策略标识
        @param limit: 返回记录数量限制（整数，默认200），返回最近的N条记录
        @return: 交易记录列表，每个元素包含策略、合约代码、时间、方向、开平、价格、数量、标记、手续费等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有策略信息，返回空列表
        if "strategies" not in self.__grp_cache__[grpid]:
            return []
            
        # 如果策略不存在，返回空列表
        if straid not in self.__grp_cache__[grpid]["strategies"]:
            return []

        # 如果缓存中没有交易记录缓存，初始化交易记录缓存字典
        if "trades" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["trades"] = dict()
        
        # 如果策略的交易记录缓存不存在，初始化缓存
        if straid not in self.__grp_cache__[grpid]["trades"]:
            # 构建交易记录CSV文件路径
            filepath = "./generated/outputs/%s/trades.csv" % (straid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表
            if not os.path.exists(filepath):
                return []
            else:
                # 创建交易记录缓存字典
                trdCache = dict()
                trdCache["file"] = filepath  # 文件路径
                trdCache["lastrow"] = 0  # 上次读取的行号
                trdCache["trades"] = list()  # 交易记录列表
                # 将缓存添加到组合缓存中
                self.__grp_cache__[grpid]["trades"][straid] = trdCache

        # 获取交易记录缓存
        trdCache = self.__grp_cache__[grpid]["trades"][straid]
        # 打开文件并读取所有行
        f = open(trdCache["file"], "r")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")
            # 如果单元格数量超过10个，跳过（可能是格式错误）
            if len(cells) > 10:
                continue

            # 创建交易记录项
            tItem = {
                "strategy":straid,  # 策略ID
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
                tItem["fee"] = float(cells[7])

            # 添加到交易记录列表
            trdCache["trades"].append(tItem)
            # 更新已读取的行号
            trdCache["lastrow"] += 1
        
        # 返回最近的limit条记录
        return trdCache["trades"][-limit:]

    def get_funds(self, grpid:str, straid:str):
        """
        获取策略的资金曲线数据
        
        读取指定策略的资金曲线CSV文件，解析为字典列表。
        如果straid为"all"，则返回所有策略的资金曲线汇总。
        使用增量读取机制，只读取新增的资金记录，并会合并实时数据。
        
        @param grpid: 组合ID（字符串），策略所属的组合标识
        @param straid: 策略ID（字符串），要查询资金曲线的策略标识，如果为"all"则返回所有策略的汇总
        @return: 资金曲线数据列表，每个元素包含策略、日期、平仓盈亏、浮动盈亏、动态权益、手续费等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有策略信息，返回空列表
        if "strategies" not in self.__grp_cache__[grpid]:
            return []
        
        # 如果策略ID不是"all"，查询单个策略的资金曲线
        if straid != "all":
            # 如果策略不存在，返回空列表
            if straid not in self.__grp_cache__[grpid]["strategies"]:
                return []

            # 如果缓存中没有资金曲线缓存，初始化资金曲线缓存字典
            if "funds" not in self.__grp_cache__[grpid]:
                self.__grp_cache__[grpid]["funds"] = dict()
            
            # 如果策略的资金曲线缓存不存在，初始化缓存
            if straid not in self.__grp_cache__[grpid]["funds"]:
                # 构建资金曲线CSV文件路径
                filepath = "./generated/outputs/%s/funds.csv" % (straid)
                filepath = os.path.join(grpInfo["path"], filepath)
                # 如果文件不存在，返回空列表
                if not os.path.exists(filepath):
                    return []
                else:
                    # 创建资金曲线缓存字典
                    trdCache = dict()
                    trdCache["file"] = filepath  # 文件路径
                    trdCache["lastrow"] = 0  # 上次读取的行号
                    trdCache["funds"] = list()  # 资金曲线数据列表
                    # 将缓存添加到组合缓存中
                    self.__grp_cache__[grpid]["funds"][straid] = trdCache

            # 获取资金曲线缓存
            trdCache = self.__grp_cache__[grpid]["funds"][straid]

            # 打开文件并读取所有行
            f = open(trdCache["file"], "r")
            last_row = trdCache["lastrow"]  # 上次读取的行号
            lines = f.readlines()
            f.close()
            # 跳过表头（第1行）和已读取的行，只读取新增的行
            lines = lines[1+last_row:]

            # 遍历新增的行，解析CSV数据
            for line in lines:
                # 按逗号分割单元格
                cells = line.split(",")
                # 如果单元格数量超过10个，跳过（可能是格式错误）
                if len(cells) > 10:
                    continue

                # 创建资金数据项
                tItem = {
                    "strategy":straid,  # 策略ID
                    "date": int(cells[0]),  # 日期
                    "closeprofit": float(cells[1]),  # 平仓盈亏
                    "dynprofit": float(cells[2]),  # 浮动盈亏
                    "dynbalance": float(cells[3]),  # 动态权益
                    "fee": 0  # 手续费，默认为0
                }

                # 如果单元格数量大于4，读取手续费
                if len(cells) > 4:
                    tItem["fee"] = float(cells[4])

                # 添加到资金曲线数据列表
                trdCache["funds"].append(tItem)
                # 更新已读取的行号
                trdCache["lastrow"] += 1

            # 复制资金曲线数据列表
            ret = trdCache["funds"].copy()

            # 获取最后一条记录的日期
            if len(ret) > 0:
                last_date = ret[-1]["date"]
            else:
                last_date = 0

            # ========== 合并实时数据 ==========
            # 读取策略的实时数据JSON文件，合并最新的资金数据
            filepath = "./generated/stradata/%s.json" % (straid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件存在，读取并合并实时数据
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)
                # 获取资金信息
                fund = json_data["fund"]
                # 如果实时数据的日期大于最后一条记录的日期，添加实时数据
                if fund["tdate"] > last_date:
                    ret.append({
                        "strategy":straid,  # 策略ID
                        "date": fund["tdate"],  # 日期
                        "closeprofit": fund["total_profit"],  # 平仓盈亏
                        "dynprofit": fund["total_dynprofit"],  # 浮动盈亏
                        "dynbalance": fund["total_profit"] + fund["total_dynprofit"] - fund["total_fees"],  # 动态权益（平仓盈亏+浮动盈亏-手续费）
                        "fee": fund["total_fees"]  # 手续费
                    })
            except:
                # 如果读取失败，忽略错误
                pass
            f.close()
            
            return ret
        else:
            # ========== 查询所有策略的资金曲线汇总 ==========
            # 创建返回列表
            ret = list()
            # 遍历所有策略
            for straid in self.__grp_cache__[grpid]["strategies"]:
                # 构建资金曲线CSV文件路径
                filepath = "./generated/outputs/%s/funds.csv" % (straid)
                filepath = os.path.join(grpInfo["path"], filepath)
                # 读取CSV文件的最后一行（用于计算增量）
                f = open(filepath, "r")
                lines = f.readlines()
                f.close()

                # 构建实时数据JSON文件路径
                filepath = "./generated/stradata/%s.json" % (straid)
                filepath = os.path.join(grpInfo["path"], filepath)
                # 如果文件不存在，跳过该策略
                if not os.path.exists(filepath):
                    continue

                # 读取实时数据JSON文件
                f = open(filepath, "r")
                content = f.read()
                f.close()
                try:
                    # 解析JSON数据
                    json_data = json.loads(content)
                    # 获取资金信息
                    fund = json_data["fund"]
                    # 获取当前日期
                    curDate = fund["tdate"]
                    # 创建资金数据项
                    item = {
                        "strategy":straid,  # 策略ID
                        "date": fund["tdate"],  # 日期
                        "closeprofit": fund["total_profit"],  # 平仓盈亏
                        "dynprofit": fund["total_dynprofit"],  # 浮动盈亏
                        "dynbalance": fund["total_profit"] + fund["total_dynprofit"] - fund["total_fees"],  # 动态权益
                        "fee": fund["total_fees"]  # 手续费
                    }

                    # 读取CSV文件的最后一行，用于计算增量
                    line = lines[-1]
                    cells = line.split(",")
                    last_date = int(cells[0])  # 最后一条记录的日期
                    # 如果当前日期等于最后一条记录的日期，使用最后一行数据
                    if last_date == curDate:
                        line = lines[-1]
                        cells = line.split(",")
                    # 获取上一条记录的平仓盈亏、动态权益和手续费
                    preprof = float(cells[1])  # 上一条记录的平仓盈亏
                    prebalance = float(cells[3])  # 上一条记录的动态权益
                    prefee = float(cells[4])  # 上一条记录的手续费

                    # 计算增量数据
                    item['profit'] = item['closeprofit']-preprof  # 当日平仓盈亏增量
                    item['thisfee'] = item['fee'] - prefee  # 当日手续费增量
                    item['addition'] = item['dynbalance']-prebalance  # 当日动态权益增量

                    # 添加到返回列表
                    ret.append(item)
                except:
                    # 如果读取失败，忽略错误
                    pass
            return ret

    def get_signals(self, grpid:str, straid:str, limit:int = 200):
        """
        获取策略的信号记录
        
        读取指定策略的信号记录CSV文件，解析为字典列表。
        使用增量读取机制，只读取新增的信号记录。
        
        @param grpid: 组合ID（字符串），策略所属的组合标识
        @param straid: 策略ID（字符串），要查询信号记录的策略标识
        @param limit: 返回记录数量限制（整数，默认200），返回最近的N条记录
        @return: 信号记录列表，每个元素包含策略、合约代码、目标、信号价格、生成时间、标记等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有策略信息，返回空列表
        if "strategies" not in self.__grp_cache__[grpid]:
            return []
            
        # 如果策略不存在，返回空列表
        if straid not in self.__grp_cache__[grpid]["strategies"]:
            return []

        # 如果缓存中没有信号记录缓存，初始化信号记录缓存字典
        if "signals" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["signals"] = dict()
        
        # 如果策略的信号记录缓存不存在，初始化缓存
        if straid not in self.__grp_cache__[grpid]["signals"]:
            # 构建信号记录CSV文件路径
            filepath = "./generated/outputs/%s/signals.csv" % (straid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表
            if not os.path.exists(filepath):
                return []
            else:
                # 创建信号记录缓存字典
                trdCache = dict()
                trdCache["file"] = filepath  # 文件路径
                trdCache["lastrow"] = 0  # 上次读取的行号
                trdCache["signals"] = list()  # 信号记录列表
                # 将缓存添加到组合缓存中
                self.__grp_cache__[grpid]["signals"][straid] = trdCache

        # 获取信号记录缓存
        trdCache = self.__grp_cache__[grpid]["signals"][straid]

        # 打开文件并读取所有行
        f = open(trdCache["file"], "r")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建信号记录项
            tItem = {
                "strategy":straid,  # 策略ID
                "code": cells[0],  # 合约代码
                "target": float(cells[1]),  # 目标价格/数量
                "sigprice": float(cells[2]),  # 信号价格
                "gentime": cells[3],  # 生成时间
                "tag": cells[4]  # 标记
            }

            # 添加到信号记录列表
            trdCache["signals"].append(tItem)

        # 更新已读取的行号（累加新增的行数）
        trdCache["lastrow"] += len(lines)        
        # 返回最近的limit条记录
        return trdCache["signals"][-limit:]

    def get_rounds(self, grpid:str, straid:str, limit:int = 200):
        """
        获取策略的交易回合记录
        
        读取指定策略的交易回合记录CSV文件，解析为字典列表。
        交易回合表示一次完整的开仓到平仓过程。
        使用增量读取机制，只读取新增的交易回合记录。
        
        @param grpid: 组合ID（字符串），策略所属的组合标识
        @param straid: 策略ID（字符串），要查询交易回合记录的策略标识
        @param limit: 返回记录数量限制（整数，默认200），返回最近的N条记录
        @return: 交易回合记录列表，每个元素包含策略、合约代码、方向、开仓时间、开仓价、平仓时间、平仓价等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有策略信息，返回空列表
        if "strategies" not in self.__grp_cache__[grpid]:
            return []
            
        # 如果策略不存在，返回空列表
        if straid not in self.__grp_cache__[grpid]["strategies"]:
            return []

        # 如果缓存中没有交易回合缓存，初始化交易回合缓存字典
        if "rounds" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["rounds"] = dict()
        
        # 如果策略的交易回合缓存不存在，初始化缓存
        if straid not in self.__grp_cache__[grpid]["rounds"]:
            # 构建交易回合CSV文件路径（closes.csv存储平仓记录）
            filepath = "./generated/outputs/%s/closes.csv" % (straid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表
            if not os.path.exists(filepath):
                return []
            else:
                # 创建交易回合缓存字典
                trdCache = dict()
                trdCache["file"] = filepath  # 文件路径
                trdCache["lastrow"] = 0  # 上次读取的行号
                trdCache["rounds"] = list()  # 交易回合记录列表
                # 将缓存添加到组合缓存中
                self.__grp_cache__[grpid]["rounds"][straid] = trdCache

        # 获取交易回合缓存
        trdCache = self.__grp_cache__[grpid]["rounds"][straid]
        # 打开文件并读取所有行
        f = open(trdCache["file"], "r")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建交易回合记录项
            tItem = {
                "strategy":straid,  # 策略ID
                "code": cells[0],  # 合约代码
                "direct": cells[1],  # 交易方向（多/空）
                "opentime": int(cells[2]),  # 开仓时间
                "openprice": float(cells[3]),  # 开仓价格
                "closetime": int(cells[4]),  # 平仓时间
                "closeprice": float(cells[5]),  # 平仓价格
                "qty": float(cells[6]),  # 数量
                "profit": float(cells[7]),  # 盈亏
                "entertag": cells[9],  # 进场标记
                "exittag": cells[10]  # 出场标记
            }

            # 添加到交易回合记录列表
            trdCache["rounds"].append(tItem)
        # 更新已读取的行号（累加新增的行数）
        trdCache["lastrow"] += len(lines)
        
        # 返回最近的limit条记录
        return trdCache["rounds"][-limit:]

    def get_positions(self, grpid:str, straid:str):
        """
        获取策略的持仓信息
        
        读取指定策略的持仓信息JSON文件，解析为字典列表。
        如果straid为"all"，则返回所有策略的持仓信息汇总。
        
        @param grpid: 组合ID（字符串），策略所属的组合标识
        @param straid: 策略ID（字符串），要查询持仓的策略标识，如果为"all"则返回所有策略的汇总
        @return: 持仓信息列表，每个元素包含策略、合约代码、方向、持仓数量、持仓均价、浮动盈亏等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有策略信息，返回空列表
        if "strategies" not in self.__grp_cache__[grpid]:
            return []
            
        # 创建返回列表
        ret = list()
        # 如果策略ID不是"all"，查询单个策略的持仓信息
        if straid != "all":
            # 如果策略不存在，返回空列表
            if straid not in self.__grp_cache__[grpid]["strategies"]:
                return []
            
            # 构建策略数据JSON文件路径
            filepath = "./generated/stradata/%s.json" % (straid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表
            if not os.path.exists(filepath):
                return []
            
            # 读取策略数据JSON文件
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)

                # 获取持仓列表
                positions = json_data["positions"]
                # 遍历所有持仓
                for pItem in positions:
                    # 兼容性处理：如果字段名为"volumn"（拼写错误），使用"volumn"，否则使用"volume"
                    tag = "volumn" if "volume" not in pItem else "volume"
                    # 如果持仓数量为0，跳过
                    if pItem[tag] == 0.0:
                        continue

                    # 遍历持仓明细
                    for dItem in pItem["details"]:
                        # 添加合约代码和策略ID
                        dItem["code"] = pItem["code"]
                        dItem["strategy"] = straid
                        # 兼容性处理：如果字段名为"volumn"（拼写错误），改为"volume"
                        if "volumn" in dItem:
                            dItem["volume"] = dItem["volumn"]
                            dItem.pop("volumn")
                        # 添加到返回列表
                        ret.append(dItem)
            except:
                # 如果读取失败，忽略错误
                pass

            f.close()
        else:
            # ========== 查询所有策略的持仓信息汇总 ==========
            # 遍历所有策略
            for straid in self.__grp_cache__[grpid]["strategies"]:
                # 构建策略数据JSON文件路径
                filepath = "./generated/stradata/%s.json" % (straid)
                filepath = os.path.join(grpInfo["path"], filepath)
                # 如果文件不存在，跳过该策略
                if not os.path.exists(filepath):
                    continue
                
                # 读取策略数据JSON文件
                f = open(filepath, "r")
                try:
                    # 读取文件内容
                    content = f.read()
                    # 解析JSON数据
                    json_data = json.loads(content)

                    # 获取持仓列表
                    positions = json_data["positions"]
                    # 遍历所有持仓
                    for pItem in positions:
                        # 兼容性处理：如果字段名为"volumn"（拼写错误），使用"volumn"，否则使用"volume"
                        tag = "volumn" if "volume" not in pItem else "volume"
                        # 如果持仓数量为0，跳过
                        if pItem[tag] == 0.0:
                            continue

                        # 遍历持仓明细
                        for dItem in pItem["details"]:
                            # 添加合约代码和策略ID
                            dItem["code"] = pItem["code"]
                            dItem["strategy"] = straid
                            # 兼容性处理：如果字段名为"volumn"（拼写错误），改为"volume"
                            if "volumn" in dItem:
                                dItem["volume"] = dItem["volumn"]
                                dItem.pop("volumn")
                            # 添加到返回列表
                            ret.append(dItem)
                except:
                    # 如果读取失败，忽略错误
                    pass

                f.close()
        return ret

    def get_channel_orders(self, grpid:str, chnlid:str, limit:int = 200):
        """
        获取交易通道的订单记录
        
        读取指定交易通道的订单记录CSV文件，解析为字典列表。
        使用增量读取机制，只读取新增的订单记录。
        
        @param grpid: 组合ID（字符串），交易通道所属的组合标识
        @param chnlid: 交易通道ID（字符串），要查询订单的交易通道标识
        @param limit: 返回记录数量限制（整数，默认200），返回最近的N条记录
        @return: 订单记录列表，每个元素包含通道、本地订单号、时间、合约代码、操作、总数量、已成交数量、价格、订单号、是否撤销、备注等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有通道信息，返回空列表
        if "channels" not in self.__grp_cache__[grpid]:
            return []
            
        # 如果通道不存在，返回空列表
        if chnlid not in self.__grp_cache__[grpid]["channels"]:
            return []

        # 如果缓存中没有订单记录缓存，初始化订单记录缓存字典
        if "corders" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["corders"] = dict()
        
        # 如果通道的订单记录缓存不存在，初始化缓存
        if chnlid not in self.__grp_cache__[grpid]["corders"]:
            # 构建订单记录CSV文件路径
            filepath = "./generated/traders/%s/orders.csv" % (chnlid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表
            if not os.path.exists(filepath):
                return []
            else:
                # 创建订单记录缓存字典
                trdCache = dict()
                trdCache["file"] = filepath  # 文件路径
                trdCache["lastrow"] = 0  # 上次读取的行号
                trdCache["corders"] = list()  # 订单记录列表
                # 将缓存添加到组合缓存中
                self.__grp_cache__[grpid]["corders"][chnlid] = trdCache

        # 获取订单记录缓存
        trdCache = self.__grp_cache__[grpid]["corders"][chnlid]

        # 打开文件并读取所有行（使用GB2312编码，忽略编码错误）
        f = open(trdCache["file"], "r",encoding="gb2312",errors="ignore")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建订单记录项
            tItem = {
                "channel":chnlid,  # 交易通道ID
                "localid":int(cells[0]),  # 本地订单号
                "time":int(cells[2]),  # 订单时间
                "code": cells[3],  # 合约代码
                "action": cells[4],  # 操作（买入/卖出）
                "total": float(cells[5]),  # 订单总数量
                "traded": float(cells[6]),  # 已成交数量
                "price": float(cells[7]),  # 订单价格
                "orderid": cells[8],  # 交易所订单号
                "canceled": cells[9],  # 是否撤销
                "remark": cells[10]  # 备注信息
            }

            # 添加到订单记录列表
            trdCache["corders"].append(tItem)
        
        # 返回最近的limit条记录
        return trdCache["corders"][-limit:]

    def get_channel_trades(self, grpid:str, chnlid:str, limit:int = 200):
        """
        获取交易通道的成交记录
        
        读取指定交易通道的成交记录CSV文件，解析为字典列表。
        使用增量读取机制，只读取新增的成交记录。
        
        @param grpid: 组合ID（字符串），交易通道所属的组合标识
        @param chnlid: 交易通道ID（字符串），要查询成交的交易通道标识
        @param limit: 返回记录数量限制（整数，默认200），返回最近的N条记录
        @return: 成交记录列表，每个元素包含通道、本地订单号、时间、合约代码、操作、数量、价格、成交号、订单号等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有通道信息，返回空列表
        if "channels" not in self.__grp_cache__[grpid]:
            return []
            
        # 如果通道不存在，返回空列表
        if chnlid not in self.__grp_cache__[grpid]["channels"]:
            return []

        # 如果缓存中没有成交记录缓存，初始化成交记录缓存字典
        if "ctrades" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["ctrades"] = dict()
        
        # 如果通道的成交记录缓存不存在，初始化缓存
        if chnlid not in self.__grp_cache__[grpid]["ctrades"]:
            # 构建成交记录CSV文件路径
            filepath = "./generated/traders/%s/trades.csv" % (chnlid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表
            if not os.path.exists(filepath):
                return []
            else:
                # 创建成交记录缓存字典
                trdCache = dict()
                trdCache["file"] = filepath  # 文件路径
                trdCache["lastrow"] = 0  # 上次读取的行号
                trdCache["ctrades"] = list()  # 成交记录列表
                # 将缓存添加到组合缓存中
                self.__grp_cache__[grpid]["ctrades"][chnlid] = trdCache

        # 获取成交记录缓存
        trdCache = self.__grp_cache__[grpid]["ctrades"][chnlid]

        # 打开文件并读取所有行（使用GB2312编码）
        f = open(trdCache["file"], "r",encoding="gb2312")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建成交记录项
            tItem = {
                "channel":chnlid,  # 交易通道ID
                "localid":int(cells[0]),  # 本地订单号
                "time":int(cells[2]),  # 成交时间
                "code": cells[3],  # 合约代码
                "action": cells[4],  # 操作（买入/卖出）
                "volume": float(cells[5]),  # 成交数量
                "price": float(cells[6]),  # 成交价格
                "tradeid": cells[7],  # 交易所成交号
                "orderid": cells[8]  # 交易所订单号
            }

            # 添加到成交记录列表
            trdCache["ctrades"].append(tItem)
        
        # 返回最近的limit条记录
        return trdCache["ctrades"][-limit:]

    def get_channel_positions(self, grpid:str, chnlid:str):
        """
        获取交易通道的持仓信息
        
        读取指定交易通道的持仓信息JSON文件，解析为字典列表。
        如果chnlid为"all"，则返回所有交易通道的持仓信息汇总。
        
        @param grpid: 组合ID（字符串），交易通道所属的组合标识
        @param chnlid: 交易通道ID（字符串），要查询持仓的交易通道标识，如果为"all"则返回所有通道的汇总
        @return: 持仓信息列表，每个元素包含通道、合约代码、方向、持仓数量、持仓均价、浮动盈亏等信息
        """
        # 如果配置字典为空，返回空列表
        if self.__config__ is None:
            return []

        # 如果配置字典中没有groups键，返回空列表
        if "groups" not in self.__config__:
            return []

        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有通道信息，返回空列表
        if "channels" not in self.__grp_cache__[grpid]:
            return []
            
        # 创建返回列表
        ret = list()
        # 创建通道列表
        channels = list()
        # 如果通道ID不是"all"，只查询指定通道
        if chnlid != 'all':
            channels.append(chnlid)
        else:
            # 否则查询所有通道
            channels = self.__grp_cache__[grpid]["channels"]

        # 遍历所有通道
        for cid in channels:
            # 如果通道不存在，跳过
            if cid not in self.__grp_cache__[grpid]["channels"]:
                continue
            
            # 构建实时数据JSON文件路径
            filepath = "./generated/traders/%s/rtdata.json" % (cid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，返回空列表（注意：这里应该是continue而不是return）
            if not os.path.exists(filepath):
                continue
            
            # 读取实时数据JSON文件
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)

                # 获取持仓列表
                positions = json_data["positions"]
                # 遍历所有持仓，添加通道ID
                for pItem in positions:
                    pItem["channel"] = cid
                    ret.append(pItem)
            except:
                # 如果读取失败，忽略错误
                pass

            f.close()
        return ret

    def get_channel_funds(self, grpid:str, chnlid:str):
        """
        获取交易通道的资金信息
        
        读取指定交易通道的资金信息JSON文件，解析为字典。
        如果chnlid为"all"，则返回所有交易通道的资金信息字典。
        
        @param grpid: 组合ID（字符串），交易通道所属的组合标识
        @param chnlid: 交易通道ID（字符串），要查询资金的交易通道标识，如果为"all"则返回所有通道的汇总
        @return: 资金信息字典，key为通道ID，value为资金信息字典（包含动态权益、盈亏、手续费等），如果通道不存在则返回None
        """
        # 如果配置字典为空，返回None
        if self.__config__ is None:
            return None

        # 如果配置字典中没有groups键，返回None
        if "groups" not in self.__config__:
            return None

        # 如果组合不存在，返回None
        if grpid not in self.__config__["groups"]:
            return None

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有通道信息，返回None
        if "channels" not in self.__grp_cache__[grpid]:
            return None
            
        # 创建返回字典
        ret = dict()
        # 创建通道列表
        channels = list()
        # 如果通道ID不是"all"，只查询指定通道
        if chnlid != 'all':
            channels.append(chnlid)
        else:
            # 否则查询所有通道
            channels = self.__grp_cache__[grpid]["channels"]

        # 遍历所有通道
        for cid in channels:
            # 如果通道不存在，跳过
            if cid not in self.__grp_cache__[grpid]["channels"]:
                continue
            
            # 构建实时数据JSON文件路径
            filepath = "./generated/traders/%s/rtdata.json" % (cid)
            filepath = os.path.join(grpInfo["path"], filepath)
            # 如果文件不存在，跳过
            if not os.path.exists(filepath):
                continue
            
            # 读取实时数据JSON文件
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)

                # 获取资金信息
                funds = json_data["funds"]
                # 将资金信息添加到返回字典，key为通道ID
                ret[cid] = funds
            except:
                # 如果读取失败，忽略错误
                pass

            f.close()
        return ret

    def get_actions(self, sdate, edate):
        """
        获取操作日志记录
        
        从数据库中查询指定时间范围内的操作日志记录。
        
        @param sdate: 开始日期（字符串），格式如"2023-01-01 00:00:00"
        @param edate: 结束日期（字符串），格式如"2023-01-31 23:59:59"
        @return: 操作日志记录列表，每个元素包含ID、登录ID、操作时间、操作IP、操作类型、备注等信息
        """
        # 创建返回列表
        ret = list()

        # 获取数据库游标
        cur = self.__db_conn__.cursor()
        # 查询指定时间范围内的操作日志（使用参数化查询，避免SQL注入）
        for row in cur.execute("SELECT id,loginid,actiontime,actionip,actiontype,remark FROM actions WHERE actiontime>=? and actiontime<=?;", (sdate, edate)):
            # 创建操作日志信息字典
            aInfo = dict()
            aInfo["id"] = row[0]  # 日志ID
            aInfo["loginid"] = row[1]  # 登录ID
            aInfo["actiontime"] = row[2]  # 操作时间
            aInfo["actionip"] = row[3]  # 操作IP地址
            aInfo["action"] = row[4]  # 操作类型
            aInfo["remark"] = row[5]  # 备注信息

            # 添加到返回列表
            ret.append(aInfo)

        return ret

    def get_group_trades(self, grpid:str):
        """
        获取组合的交易记录
        
        读取组合的交易记录CSV文件，解析为字典列表。
        使用增量读取机制，只读取新增的交易记录。
        
        @param grpid: 组合ID（字符串），要查询交易记录的组合标识
        @return: 交易记录列表，每个元素包含合约代码、时间、方向、开平、价格、数量、手续费等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有组合交易记录缓存，初始化组合交易记录缓存字典
        if "grptrades" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["grptrades"] = dict()
        
        # 构建组合交易记录CSV文件路径
        filepath = "./generated/portfolio/trades.csv"
        filepath = os.path.join(grpInfo["path"], filepath)
        # 如果文件不存在，返回空列表
        if not os.path.exists(filepath):
            return []
        else:
            # 创建交易记录缓存字典
            trdCache = dict()
            trdCache["file"] = filepath  # 文件路径
            trdCache["lastrow"] = 0  # 上次读取的行号
            trdCache["trades"] = list()  # 交易记录列表
            # 将缓存添加到组合缓存中
            self.__grp_cache__[grpid]["grptrades"]["cache"] = trdCache

        # 获取交易记录缓存
        trdCache = self.__grp_cache__[grpid]["grptrades"]['cache']

        # 打开文件并读取所有行
        f = open(trdCache["file"], "r")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建交易记录项
            tItem = {
                "code": cells[0],  # 合约代码
                "time": int(cells[1]),  # 交易时间
                "direction": cells[2],  # 交易方向（买入/卖出）
                "offset": cells[3],  # 开平标志（开仓/平仓）
                "price": float(cells[4]),  # 成交价格
                "volume": float(cells[5]),  # 成交数量
                "fee": float(cells[6])  # 手续费
            }

            # 添加到交易记录列表
            trdCache["trades"].append(tItem)
            # 更新已读取的行号
            trdCache["lastrow"] += 1
        
        return trdCache["trades"]

    def get_group_rounds(self, grpid:str):
        """
        获取组合的交易回合记录
        
        读取组合的交易回合记录CSV文件，解析为字典列表。
        交易回合表示一次完整的开仓到平仓过程。
        使用增量读取机制，只读取新增的交易回合记录。
        
        @param grpid: 组合ID（字符串），要查询交易回合的组合标识
        @return: 交易回合记录列表，每个元素包含合约代码、方向、开仓时间、开仓价、平仓时间、平仓价、数量、盈亏等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有组合交易回合缓存，初始化组合交易回合缓存字典
        if "grprounds" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["grprounds"] = dict()
        
        # 构建组合交易回合CSV文件路径
        filepath = "./generated/portfolio/closes.csv"
        filepath = os.path.join(grpInfo["path"], filepath)
        # 如果文件不存在，返回空列表
        if not os.path.exists(filepath):
            return []
        else:
            # 创建交易回合缓存字典
            trdCache = dict()
            trdCache["file"] = filepath  # 文件路径
            trdCache["lastrow"] = 0  # 上次读取的行号
            trdCache["rounds"] = list()  # 交易回合记录列表
            # 将缓存添加到组合缓存中
            self.__grp_cache__[grpid]["grprounds"]["cache"] = trdCache

        # 获取交易回合缓存
        trdCache = self.__grp_cache__[grpid]["grprounds"]['cache']

        # 打开文件并读取所有行
        f = open(trdCache["file"], "r")
        last_row = trdCache["lastrow"]  # 上次读取的行号
        lines = f.readlines()
        f.close()
        # 跳过表头（第1行）和已读取的行，只读取新增的行
        lines = lines[1+last_row:]

        # 遍历新增的行，解析CSV数据
        for line in lines:
            # 按逗号分割单元格
            cells = line.split(",")

            # 创建交易回合记录项
            tItem = {
                "code": cells[0],  # 合约代码
                "direct": cells[1],  # 交易方向（多/空）
                "opentime": int(cells[2]),  # 开仓时间
                "openprice": float(cells[3]),  # 开仓价格
                "closetime": int(cells[4]),  # 平仓时间
                "closeprice": float(cells[5]),  # 平仓价格
                "qty": float(cells[6]),  # 数量
                "profit": float(cells[7])  # 盈亏
            }

            # 添加到交易回合记录列表
            trdCache["rounds"].append(tItem)
            # 更新已读取的行号
            trdCache["lastrow"] += 1
        
        return trdCache["rounds"]

    def get_group_funds(self, grpid:str):
        """
        获取组合的资金曲线数据
        
        读取组合的资金曲线CSV文件，解析为字典列表。
        使用增量读取机制，只读取新增的资金记录，并会合并实时数据。
        
        @param grpid: 组合ID（字符串），要查询资金曲线的组合标识
        @return: 资金曲线数据列表，每个元素包含日期、前一日动态权益、前一日权益、动态权益、平仓盈亏、浮动盈亏、手续费、最大动态权益、最大时间、最小动态权益、最小时间、月度最大权益、月度最大日期、月度最小权益、月度最小日期等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 如果缓存中没有组合资金曲线缓存，初始化组合资金曲线缓存字典
        if "grpfunds" not in self.__grp_cache__[grpid]:
            self.__grp_cache__[grpid]["grpfunds"] = dict()
        
        # 构建组合资金曲线CSV文件路径
        filepath = "./generated/portfolio/funds.csv"
        filepath = os.path.join(grpInfo["path"], filepath)
        # 如果文件存在，初始化缓存
        if os.path.exists(filepath):
            # 创建资金曲线缓存字典
            trdCache = dict()
            trdCache["file"] = filepath  # 文件路径
            trdCache["lastrow"] = 0  # 上次读取的行号
            trdCache["funds"] = list()  # 资金曲线数据列表
            # 将缓存添加到组合缓存中
            self.__grp_cache__[grpid]["grpfunds"]["cache"] = trdCache

        # 获取资金曲线缓存
        trdCache = None
        if "cache" in self.__grp_cache__[grpid]["grpfunds"]:
            trdCache = self.__grp_cache__[grpid]["grpfunds"]['cache']

        # 创建返回列表
        ret = []
        # 如果缓存存在，读取新增的资金记录
        if trdCache is not None:
            # 打开文件并读取所有行
            f = open(trdCache["file"], "r")
            last_row = trdCache["lastrow"]  # 上次读取的行号
            lines = f.readlines()
            f.close()
            # 跳过表头（第1行）和已读取的行，只读取新增的行
            lines = lines[1+last_row:]

            # 遍历新增的行，解析CSV数据
            for line in lines:
                # 按逗号分割单元格
                cells = line.split(",")

                # 创建资金数据项
                tItem = {
                    "date": int(cells[0]),  # 日期
                    "predynbalance": float(cells[1]),  # 前一日动态权益
                    "prebalance": float(cells[2]),  # 前一日权益
                    "balance": float(cells[3]),  # 动态权益
                    "closeprofit": float(cells[4]),  # 平仓盈亏
                    "dynprofit": float(cells[5]),  # 浮动盈亏
                    "fee": float(cells[6]),  # 手续费
                    "maxdynbalance": float(cells[7]),  # 最大动态权益
                    "maxtime": float(cells[8]),  # 最大时间
                    "mindynbalance": float(cells[9]),  # 最小动态权益
                    "mintime": float(cells[10]),  # 最小时间
                    "mdmaxbalance": float(cells[11]),  # 月度最大权益
                    "mdmaxdate": float(cells[12]),  # 月度最大日期
                    "mdminbalance": float(cells[13]),  # 月度最小权益
                    "mdmindate": float(cells[14])  # 月度最小日期
                }

                # 添加到资金曲线数据列表
                trdCache["funds"].append(tItem)
                # 更新已读取的行号
                trdCache["lastrow"] += 1
            
            # 复制资金曲线数据列表
            ret = trdCache["funds"].copy()

            # 获取最后一条记录的日期
            if len(ret) > 0:
                last_date = ret[-1]["date"]
            else:
                last_date = 0
        else:
            last_date = 0

        # ========== 合并实时数据 ==========
        # 读取组合的实时数据JSON文件，合并最新的资金数据
        filepath = "./generated/portfolio/datas.json"
        filepath = os.path.join(grpInfo["path"], filepath)
        # 如果文件存在，读取并合并实时数据
        if os.path.exists(filepath):
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)
                # 获取资金信息
                fund = json_data["fund"]
                # 如果实时数据的日期大于最后一条记录的日期，添加实时数据
                if fund["date"] > last_date:
                    ret.append({
                        "date": fund["date"],  # 日期
                        "predynbalance": fund["predynbal"],  # 前一日动态权益
                        "prebalance": fund["prebalance"],  # 前一日权益
                        "balance": fund["balance"],  # 动态权益
                        "closeprofit": fund["profit"],  # 平仓盈亏
                        "dynprofit": fund["dynprofit"],  # 浮动盈亏
                        "fee": fund["fees"],  # 手续费
                        "maxdynbalance": fund["max_dyn_bal"],  # 最大动态权益
                        "maxtime": fund["max_time"],  # 最大时间
                        "mindynbalance": fund["min_dyn_bal"],  # 最小动态权益
                        "mintime": fund["min_time"],  # 最小时间
                        "mdmaxbalance": fund["maxmd"]["dyn_balance"],  # 月度最大权益
                        "mdmaxdate": fund["maxmd"]["date"],  # 月度最大日期
                        "mdminbalance": fund["minmd"]["dyn_balance"],  # 月度最小权益
                        "mdmindate": fund["minmd"]["date"]  # 月度最小日期
                    })
            except:
                # 如果读取失败，忽略错误
                pass
            f.close()
        return ret

    def get_group_positions(self, grpid:str):
        """
        获取组合的持仓信息
        
        读取组合的持仓信息JSON文件，解析为字典列表。
        
        @param grpid: 组合ID（字符串），要查询持仓的组合标识
        @return: 持仓信息列表，每个元素包含合约代码、方向、持仓数量、持仓均价、浮动盈亏等信息
        """
        # 如果组合不存在，返回空列表
        if grpid not in self.__config__["groups"]:
            return []

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)
        
        # 构建组合实时数据JSON文件路径
        filepath = "./generated/portfolio/datas.json"
        filepath = os.path.join(grpInfo["path"], filepath)
        # 如果文件不存在，返回空列表
        if not os.path.exists(filepath):
            return []
        else:
            # 创建返回列表
            ret = list()
            # 读取实时数据JSON文件
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)

                # 获取持仓列表
                positions = json_data["positions"]
                # 遍历所有持仓
                for pItem in positions:
                    # 如果持仓数量为0，跳过
                    if pItem["volume"] == 0:
                        continue

                    # 遍历持仓明细
                    for dItem in pItem["details"]:
                        # 添加合约代码
                        dItem["code"] = pItem["code"]
                        # 添加到返回列表
                        ret.append(dItem)
            except:
                # 如果读取失败，忽略错误
                pass

            f.close()
            return ret

    def get_group_performances(self, grpid:str):
        """
        获取组合的性能统计信息
        
        读取组合的性能统计信息JSON文件，解析为字典。
        性能统计包括每个合约的盈亏、胜率等指标。
        
        @param grpid: 组合ID（字符串），要查询性能统计的组合标识
        @return: 性能统计字典，key为合约代码，value为性能统计信息（包含盈亏、胜率等）
        """
        # 如果组合不存在，返回空字典
        if grpid not in self.__config__["groups"]:
            return {}

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)
        
        # 构建组合实时数据JSON文件路径
        filepath = "./generated/portfolio/datas.json" 
        filepath = os.path.join(grpInfo["path"], filepath)
        # 如果文件不存在，返回空字典
        if not os.path.exists(filepath):
            return {}
        else:
            # 创建性能统计字典
            perf = dict()
            # 读取实时数据JSON文件
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 解析JSON数据
                json_data = json.loads(content)

                # 获取持仓列表
                positions = json_data["positions"]
                # 遍历所有持仓，提取性能统计信息
                for pItem in positions:
                    # 获取合约代码
                    code = pItem['code']
                    # 按点号分割合约代码
                    ay = code.split(".")
                    # 默认使用完整合约代码作为产品ID
                    pid = code
                    # 如果合约代码包含多个部分，提取产品ID（品种代码）
                    if len(ay) > 2:
                        # 如果第二部分不是指数、股票、ETF，则使用前两部分作为产品ID
                        if ay[1] not in ['IDX','STK','ETF']:
                            pid = ay[0] + "." + ay[1]
                        else:
                            # 否则使用第一部分和第三部分作为产品ID
                            pid = ay[0] + "." + ay[2]

                    # 如果产品ID不在性能统计字典中，初始化性能统计
                    if pid not in perf:
                        perf[pid] = {
                            'closeprofit':0,  # 平仓盈亏
                            'dynprofit':0  # 浮动盈亏
                        }

                    # 累加平仓盈亏和浮动盈亏
                    perf[pid]['closeprofit'] += pItem['closeprofit']
                    perf[pid]['dynprofit'] += pItem['dynprofit']
                    
            except:
                # 如果读取失败，忽略错误
                pass

            f.close()
            return perf

    def get_group_filters(self, grpid:str):
        """
        获取组合的过滤器配置
        
        读取组合的过滤器配置文件（filters.json或filters.yaml），解析为字典。
        过滤器用于控制策略、执行器、合约代码的显示和过滤。
        
        @param grpid: 组合ID（字符串），要查询过滤器配置的组合标识
        @return: 过滤器配置字典，包含strategy_filters（策略过滤器）、code_filters（合约过滤器）、executer_filters（执行器过滤器）
        """
        # 如果组合不存在，返回空字典
        if grpid not in self.__config__["groups"]:
            return {}

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)
        
        # 先尝试读取filters.json文件
        filepath = os.path.join(grpInfo["path"], 'filters.json')
        isYaml = False
        # 如果filters.json不存在，尝试读取filters.yaml文件
        if not os.path.exists(filepath):
            filepath = os.path.join(grpInfo["path"], 'filters.yaml')
            isYaml = True
        
        # 如果文件不存在，初始化为空字典
        if not os.path.exists(filepath):
            filters = {}
        else:
            # 读取过滤器配置文件
            filters = {}
            f = open(filepath, "r")
            try:
                # 读取文件内容
                content = f.read()
                # 如果是YAML文件，使用yaml.full_load解析
                if isYaml:
                    filters = yaml.full_load(content)
                else:
                    # 否则使用json.loads解析
                    filters = json.loads(content)
            except:
                # 如果读取失败，忽略错误
                pass

            f.close()

        # 获取组合缓存
        gpCache = self.__grp_cache__[grpid]
        # 如果过滤器配置中没有executer_filters，初始化为空字典
        if "executer_filters" not in filters:
            filters["executer_filters"] = dict()
        # 如果过滤器配置中没有strategy_filters，初始化为空字典
        if "strategy_filters" not in filters:
            filters["strategy_filters"] = dict()
        # 如果过滤器配置中没有code_filters，初始化为空字典
        if "code_filters" not in filters:
            filters["code_filters"] = dict()

        # 如果缓存中有策略列表，为每个策略初始化过滤器（如果不存在）
        if "strategies" in gpCache:
            for sid in gpCache["strategies"]:
                if sid not in filters['strategy_filters']:
                    filters['strategy_filters'][sid] = False
        
        # 如果缓存中有执行器列表，为每个执行器初始化过滤器（如果不存在）
        if "executers" in gpCache:
            for eid in gpCache["executers"]:
                if eid not in filters['executer_filters']:
                    filters['executer_filters'][eid] = False

        # 规范化策略过滤器：如果值不是布尔类型，则设置为True
        for id in filters['strategy_filters'].keys():
            if type(filters['strategy_filters'][id]) != bool:
                filters['strategy_filters'][id] = True

        # 规范化合约过滤器：如果值不是布尔类型，则设置为True
        for id in filters['code_filters'].keys():
            if type(filters['code_filters'][id]) != bool:
                filters['code_filters'][id] = True

        return filters

    def set_group_filters(self, grpid:str, filters:dict):
        """
        设置组合的过滤器配置
        
        将过滤器配置写入组合的过滤器配置文件（filters.json或filters.yaml）。
        过滤器用于控制策略、执行器、合约代码的显示和过滤。
        
        @param grpid: 组合ID（字符串），要设置过滤器配置的组合标识
        @param filters: 过滤器配置字典，包含strategy_filters（策略过滤器）、code_filters（合约过滤器）、executer_filters（执行器过滤器）
        @return: 如果设置成功返回True，否则返回False
        """
        # 如果组合不存在，返回False
        if grpid not in self.__config__["groups"]:
            return False

        # 获取组合信息
        grpInfo = self.__config__["groups"][grpid]
        # 检查并更新缓存
        self.__check_cache__(grpid, grpInfo)

        # 创建真实的过滤器配置字典（只包含启用项）
        realfilters = {
            "strategy_filters":{},  # 策略过滤器
            "code_filters":{},  # 合约过滤器
            "executer_filters":{}  # 执行器过滤器
        }

        # 处理策略过滤器：只保存启用项（值为True的项）
        if "strategy_filters" in filters:
            for sid in filters["strategy_filters"]:
                if filters["strategy_filters"][sid]:
                    realfilters["strategy_filters"][sid] = {
                        "action":"redirect",  # 动作类型：重定向
                        "target":0  # 目标值
                    }

        # 处理合约过滤器：只保存启用项（值为True的项）
        if "code_filters" in filters:
            for sid in filters["code_filters"]:
                if filters["code_filters"][sid]:
                    realfilters["code_filters"][sid] = {
                        "action":"redirect",  # 动作类型：重定向
                        "target":0  # 目标值
                    }

        # 处理执行器过滤器：直接复制（执行器过滤器可能包含更复杂的配置）
        if "executer_filters" in filters:
            realfilters["executer_filters"] = filters["executer_filters"]
        
        # 先尝试写入filters.json文件
        filepath = os.path.join(grpInfo["path"], 'filters.json')
        isYaml = False
        # 如果filters.json不存在，使用filters.yaml文件
        if not os.path.exists(filepath):
            filepath = os.path.join(grpInfo["path"], 'filters.yaml')
            isYaml = True
        # 备份原文件
        backup_file(filepath)
        # 打开文件并写入过滤器配置
        f = open(filepath, "w")
        # 如果是YAML文件，使用yaml.dump写入
        if isYaml:
            yaml.dump(realfilters, f, indent=4, allow_unicode=True)
        else:
            # 否则使用json.dumps写入JSON格式
            f.write(json.dumps(realfilters, indent=4))
        f.close()
        return True
            