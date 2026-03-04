from user import User

def entrypoint():
    """测试入口：故意少传 name 参数以制造 bug。"""
    # 这里少传了必须的 name 参数，会触发 TypeError
    user = User(name="test_user")



if __name__ == "__main__":
    entrypoint()

