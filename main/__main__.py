"""
允许通过 ``python -m main`` 运行流水线。

Python 的 ``-m`` 标志会查找包的 ``__main__.py`` 并执行。
没有这个文件的话，``python -m main`` 会报错：
    "No module named main.__main__; 'main' is a package and cannot be directly executed"
"""

from main import main

main()
