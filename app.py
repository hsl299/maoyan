# -*- coding: utf-8 -*-
"""
仿猫眼电影/演出票务系统 - 应用主入口
运行：python app.py
访问：http://127.0.0.1:5000
"""
from flask import Flask
import config
import db
from routes.auth import auth_bp
from routes.user import user_bp
from routes.merchant import merchant_bp


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(merchant_bp)
    # 请求结束自动关闭数据库连接
    app.teardown_appcontext(db.close_conn)
    return app


app = create_app()


if __name__ == '__main__':
    print('=' * 50)
    print('仿猫眼票务系统已启动')
    print('用户端/后台首页:  http://127.0.0.1:5000/')
    print('商家后台:         http://127.0.0.1:5000/merchant/')
    print('=' * 50)
    app.run(host='127.0.0.1', port=5000, debug=True)
