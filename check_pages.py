# -*- coding: utf-8 -*-
"""补测：遍历所有页面，确认无 500 / Jinja 渲染错误"""
import urllib.parse
import urllib.request
import http.cookiejar

BASE = 'http://127.0.0.1:5000'


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def post(self, path, data=None):
        body = urllib.parse.urlencode(data or {})
        req = urllib.request.Request(BASE + path, data=body.encode(),
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with self.opener.open(req) as r:
            return r.status, r.read().decode()

    def get(self, path):
        path = urllib.parse.quote(path, safe='/?&=:%')
        req = urllib.request.Request(BASE + path, headers={'User-Agent': 'test'})
        with self.opener.open(req) as r:
            return r.status, r.read().decode()


def probe(client, paths, label):
    bad = []
    for p in paths:
        try:
            s, _ = client.get(p)
            if s != 200:
                bad.append((p, s))
        except Exception as e:
            bad.append((p, f'EXC {e}'))
    print(f'[{label}] {len(paths)} 页，异常 {len(bad)}')
    for p, s in bad:
        print('   非200:', p, s)
    return not bad


# 未登录可访问
anon = Client()
ok = probe(anon, ['/', '/login', '/register'], '未登录公开页')

# 普通用户
u = Client()
u.post('/login', {'username': 'user01', 'password': '123456'})
u_paths = ['/', '/my_orders', '/order/1', '/order/1/ticket']
ok &= probe(u, u_paths, '用户端')

# 商家
m = Client()
m.post('/login', {'username': 'shop01', 'password': '123456'})
m_paths = ['/merchant/', '/merchant/tickets', '/merchant/tickets/new',
           '/merchant/orders', '/merchant/refunds', '/merchant/verify',
           '/merchant/tickets/1/edit', '/merchant/tickets/1/sessions']
ok &= probe(m, m_paths, '商家端')

# 场次座位管理 / 座位图（用真实场次与座位）
import pymysql, config
c = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
                    password=config.DB_PASSWORD, database=config.DB_NAME, charset='utf8mb4')
cur = c.cursor(pymysql.cursors.DictCursor)
cur.execute('SELECT id FROM sessions LIMIT 1'); srow = cur.fetchone()
cur.execute('SELECT id FROM tickets LIMIT 1'); trow = cur.fetchone()
cur.execute('SELECT id FROM orders LIMIT 1'); orow = cur.fetchone()
c.close()
if srow:
    ok &= probe(m, [f'/merchant/sessions/{srow["id"]}/seats'], '商家座位管理')
    ok &= probe(u, [f'/select_seat/{srow["id"]}'], '用户选座页')
if trow:
    ok &= probe(u, [f'/ticket/{trow["id"]}'], '用户详情')
if orow:
    ok &= probe(u, [f'/order/{orow["id"]}/confirm'], '订单确认页')

print('\n页面巡检', '全部通过' if ok else '存在异常')
