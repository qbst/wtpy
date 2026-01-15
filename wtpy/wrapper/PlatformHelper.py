"""
平台辅助工具模块

本模块提供跨平台支持功能，主要用于：
1. 检测Python运行环境的架构（32位/64位）
2. 检测操作系统类型（Windows/Linux）
3. 根据平台自动生成动态库文件名（.dll/.so）
4. 处理不同平台的字符串编码问题（Windows使用GBK，Linux使用UTF-8）

这些功能对于在不同操作系统和架构下正确加载C++动态链接库至关重要。
"""

# 导入platform模块，用于获取系统平台信息
import platform

class PlatformHelper:
    """
    平台辅助工具类
    
    提供跨平台的工具方法，用于处理平台相关的差异，如动态库路径、字符串编码等。
    所有方法都是静态方法，可以直接通过类名调用。
    """

    @staticmethod
    def isPythonX64() -> bool:
        """
        检测当前Python运行环境是否为64位架构
        
        @return bool: True表示64位，False表示32位
        """
        # 获取Python解释器的架构信息
        ret = platform.architecture()
        # 返回是否为64位架构
        return (ret[0] == "64bit")

    @staticmethod
    def isWindows() -> bool:
        """
        检测当前操作系统是否为Windows平台
        
        @return bool: True表示Windows平台，False表示其他平台（主要是Linux）
        """
        # 获取系统名称并转换为小写进行比较
        if "windows" in platform.system().lower():
            return True

        return False

    @staticmethod
    def getModule(moduleName:str, subdir:str="") -> str:
        """
        根据平台和架构生成动态库文件的相对路径
        
        Windows平台：
        - 64位：x64/moduleName.dll
        - 32位：x86/moduleName.dll
        
        Linux平台：
        - linux/libmoduleName.so
        
        @param moduleName: 模块名称（不含扩展名和前缀）
        @param subdir: 可选的子目录名称
        @return str: 动态库文件的相对路径
        """
        # 初始化变量
        dllname = ""  # 动态库路径
        ext = ""      # 文件扩展名
        prefix = ""   # 文件名前缀（Linux需要lib前缀）
        
        # 判断是否为Windows平台
        if PlatformHelper.isWindows(): #windows平台
            # Windows平台使用.dll扩展名
            ext = ".dll"
            # 根据Python架构选择对应的目录
            if PlatformHelper.isPythonX64():
                dllname = "x64/"  # 64位使用x64目录
            else:
                dllname = "x86/"  # 32位使用x86目录
        else:#Linux平台
            # Linux平台使用linux目录
            dllname = "linux/"
            # Linux平台动态库需要lib前缀
            prefix = "lib"
            # Linux平台使用.so扩展名
            ext = ".so"

        # 如果指定了子目录，则添加到路径中
        if subdir != "":
            dllname += subdir + "/"

        # 拼接完整的动态库文件名：路径 + 前缀 + 模块名 + 扩展名
        dllname += prefix + moduleName + ext
        return dllname
    
    @staticmethod
    def auto_encode(s:str) -> bytes:
        """
        根据平台自动进行字符串编码转换
        
        Windows平台：将UTF-8字符串转换为GBK编码（Windows中文系统默认编码）
        Linux平台：保持UTF-8编码
        
        这是因为C++底层库在不同平台使用的编码不同，需要统一处理。
        
        @param s: 待编码的字符串（UTF-8格式）
        @return bytes: 编码后的字节串
        """
        # 判断是否为Windows平台
        if PlatformHelper.isWindows():
            # Windows平台：UTF-8 -> GBK（Windows中文系统默认编码）
            return bytes(s, encoding = "utf-8").decode('utf-8').encode('gbk')
        else:
            # Linux平台：保持UTF-8编码
            return bytes(s, encoding = "utf-8")
            