"""
工具函数定义模块

本模块提供了一些通用的工具函数和装饰器，用于支持框架的基础功能。
主要包括单例模式装饰器和废弃函数装饰器，这些工具函数被框架的其他模块广泛使用。

主要功能：
1. singleton装饰器：实现单例模式，确保某个类只有一个实例
2. deprecated装饰器：标记已废弃的函数，调用时输出警告信息
"""

def singleton(cls):
    """
    单例模式装饰器
    
    使用该装饰器修饰的类将变成单例模式，无论创建多少次实例，都只会返回同一个对象。
    这对于需要全局唯一实例的类（如引擎类、管理器类）非常有用。
    
    @cls: 要修饰的类对象
    @return: 返回一个包装函数，该函数会检查并返回类的唯一实例
    """
    # 存储已创建的实例，键为类对象，值为类的实例
    instances = {}
    def getinstance(*args,**kwargs):
        """
        获取类实例的内部函数
        
        @*args: 位置参数，传递给类的构造函数
        @**kwargs: 关键字参数，传递给类的构造函数
        @return: 返回类的唯一实例
        """
        # 如果该类还没有创建过实例，则创建新实例并存储
        if cls not in instances:
            instances[cls] = cls(*args,**kwargs)
        # 返回已存在的实例
        return instances[cls]
    return getinstance


def deprecated(func):
    """
    废弃函数装饰器
    
    使用该装饰器修饰的函数在被调用时会输出警告信息，提示该函数已被废弃。
    这有助于在API演进过程中提醒用户使用新的替代函数。
    
    @func: 要标记为废弃的函数对象
    @return: 返回一个包装函数，该函数会输出警告并调用原函数
    """
    def wrapper(*args, **kwargs):
        """
        包装函数，在调用原函数前输出废弃警告
        
        @*args: 位置参数，传递给原函数
        @**kwargs: 关键字参数，传递给原函数
        @return: 返回原函数的执行结果
        """
        # 构造并输出警告信息
        msg = f"Warning: {func.__name__} is deprecated."
        print(msg)
        # 调用原函数并返回结果
        return func(*args, **kwargs)
    return wrapper
