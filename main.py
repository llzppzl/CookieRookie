"""兼容旧用法：python main.py [--interactive | "bug 描述"]

推荐安装后直接使用 cookierookie 命令，见 README。
"""

from cookierookie.cli import run

if __name__ == "__main__":
    run()
