from typing import Any


class LazySetupMethod:
    def __call__(self, instance_or_class) -> Any:
        pass


class LazyAttr(object):
    """ If accessed ONLY by instance, we will replace ourselves with result of calling func.
        If accessed via class, we return self so you can see the LazyAttr, and so it is not
        evaluated unless we are called via a real instance.
    """
    def __init__(self, func, name=None):
        self.func = func
        self.name = name if name is not None else func.__name__
        self.__doc__ = func.__doc__

    def __get__(self, instance, class_):
        if instance is None:
            return self
        res = self.func(instance)
        setattr(instance, self.name, res)
        return res

    # def __set_name__(self, owner, name):
    #     self.name = name


class LazyClassAttr(object):
    """ If accessed via class or instance, we will replace on both by rhe result of executing
        the `func` function that was passed into `LazyClassAttr.__init__`.

        Whatever this passed-in method returns is the value that will be set on the class/instance
        (depending on how we are accessed, if via instance or class, whatever it is that's what
        is replaced).

        To see an example of this in use, look inside code for method
        `xmodel.base.model.BaseModel.__init_subclass__`.  That method sets one of these on
        `xmodel.base.model.BaseModel.api`, to lazy-load it when it's first accessed.
    """
    def __init__(self, func, name=None):
        self._setup_func = func
        self.name = name if name is not None else func.__name__
        self.__doc__ = func.__doc__

    def __get__(self, instance, class_):
        result = self._setup_func(instance or class_)
        if instance is not None:
            setattr(instance, self.name, result)

        if class_ is not None:
            setattr(class_, self.name, result)

        return result
