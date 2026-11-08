-- =====================================================================
-- 仿猫眼电影/演出票务系统 - 数据库初始化脚本
-- 用法：在 MySQL 中执行本脚本（mysql -u root -p < db.sql 或图形工具导入）
-- =====================================================================

CREATE DATABASE IF NOT EXISTS maoyan_ticket DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE maoyan_ticket;

-- ---------------------------------------------------------------------
-- 1. 用户表（role: 0=普通用户, 1=商家）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS users;
CREATE TABLE users (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username    VARCHAR(50)  NOT NULL UNIQUE COMMENT '登录名',
    password    VARCHAR(255) NOT NULL COMMENT '密码哈希',
    nickname    VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '昵称',
    phone       VARCHAR(20)  NOT NULL DEFAULT '' COMMENT '手机号',
    role        TINYINT      NOT NULL DEFAULT 0 COMMENT '0普通用户 1商家',
    avatar      VARCHAR(255) NOT NULL DEFAULT '' COMMENT '头像',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ---------------------------------------------------------------------
-- 2. 票品表（type: 0=电影, 1=演出; status: 1=上架, 0=下架）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS tickets;
CREATE TABLE tickets (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    merchant_id INT UNSIGNED NOT NULL COMMENT '所属商家',
    title       VARCHAR(100) NOT NULL COMMENT '票品名称',
    type        TINYINT      NOT NULL DEFAULT 0 COMMENT '0电影 1演出',
    cover       VARCHAR(255) NOT NULL DEFAULT '' COMMENT '封面图',
    intro       TEXT         COMMENT '简介',
    actors      VARCHAR(255) NOT NULL DEFAULT '' COMMENT '演员/嘉宾',
    duration    INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '时长(分钟)',
    address     VARCHAR(255) NOT NULL DEFAULT '' COMMENT '放映/演出地址',
    status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1上架 0下架',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_merchant (merchant_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='票品表';

-- ---------------------------------------------------------------------
-- 3. 场次表（不同场次不同票价/库存）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS sessions;
CREATE TABLE sessions (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    ticket_id   INT UNSIGNED NOT NULL,
    show_time   DATETIME     NOT NULL COMMENT '放映/演出时间',
    base_price  DECIMAL(8,2) NOT NULL DEFAULT 0 COMMENT '基础票价',
    seat_rows   INT          NOT NULL DEFAULT 8 COMMENT '座位行数',
    seat_cols   INT          NOT NULL DEFAULT 10 COMMENT '座位列数',
    status      TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0停售',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_ticket (ticket_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场次表';

-- ---------------------------------------------------------------------
-- 4. 座位表（status: 0=可售, 1=锁定, 2=已售; price为座位实际售价）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS seats;
CREATE TABLE seats (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    session_id  INT UNSIGNED NOT NULL,
    seat_row    VARCHAR(5)   NOT NULL COMMENT '行号(A-Z)',
    seat_col    INT          NOT NULL COMMENT '列号',
    price       DECIMAL(8,2) NOT NULL DEFAULT 0 COMMENT '座位价格',
    status      TINYINT      NOT NULL DEFAULT 0 COMMENT '0可售 1锁定 2已售',
    PRIMARY KEY (id),
    KEY idx_session (session_id),
    UNIQUE KEY uk_seat (session_id, seat_row, seat_col)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='座位表';

-- ---------------------------------------------------------------------
-- 5. 订单表（status: 0待支付 1已支付 2已完成 3已退票 4已取消 5退票审核中 6已核销）
--    核销码为订单级：一个订单无论几张票，共用同一个核销码
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS orders;
CREATE TABLE orders (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no    VARCHAR(32)  NOT NULL UNIQUE COMMENT '订单号',
    user_id     INT UNSIGNED NOT NULL,
    session_id  INT UNSIGNED NOT NULL,
    total_price DECIMAL(10,2)NOT NULL DEFAULT 0,
    status      TINYINT      NOT NULL DEFAULT 0 COMMENT '0待支付 1已支付 2已完成 3已退票 4已取消 5退票审核中 6已核销',
    verify_code VARCHAR(32)  NULL COMMENT '订单统一核销码(一个订单共用一个)',
    verify_time DATETIME     NULL COMMENT '订单核销时间',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at     DATETIME     NULL,
    PRIMARY KEY (id),
    KEY idx_user (user_id),
    KEY idx_session (session_id),
    KEY idx_status (status),
    KEY idx_verify_code (verify_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

-- ---------------------------------------------------------------------
-- 6. 订单座位关联表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS order_seats;
CREATE TABLE order_seats (
    id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id INT UNSIGNED NOT NULL,
    seat_id  INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    KEY idx_seat (seat_id),
    KEY idx_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单座位表';

-- ---------------------------------------------------------------------
-- 7. 电子票券表（status: 0未核销 1已核销；核销码统一存订单表，本表不再单独存核销码）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS e_tickets;
CREATE TABLE e_tickets (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id   INT UNSIGNED NOT NULL,
    seat_id    INT UNSIGNED NOT NULL COMMENT '对应座位',
    status     TINYINT      NOT NULL DEFAULT 0 COMMENT '0未核销 1已核销',
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at DATETIME    NULL,
    PRIMARY KEY (id),
    KEY idx_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='电子票券表';

-- ---------------------------------------------------------------------
-- 8. 退票申请表（status: 0待审核 1通过 2不通过）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS refunds;
CREATE TABLE refunds (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id   INT UNSIGNED NOT NULL,
    user_id    INT UNSIGNED NOT NULL,
    reason     VARCHAR(255) NOT NULL DEFAULT '' COMMENT '退票原因',
    status     TINYINT      NOT NULL DEFAULT 0 COMMENT '0待审核 1通过 2不通过',
    reply      VARCHAR(255) NOT NULL DEFAULT '' COMMENT '审核意见',
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at DATETIME     NULL,
    PRIMARY KEY (id),
    KEY idx_order (order_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='退票申请表';

-- =====================================================================
-- 示例数据（票品 / 场次 / 座位）
-- 说明：示例用户账号（shop01 / user01，密码 123456）由 init_db.py
--       通过 Python 正确生成密码哈希后写入，不在本 SQL 中插入。
-- =====================================================================

-- 票品
INSERT INTO tickets (merchant_id, title, type, cover, intro, actors, duration, address) VALUES
(1, '流浪地球3', 0, '', '太阳急速老化，人类启动"移山计划"，带着地球一起逃离太阳系，开启2500年的星际流浪之旅。本片为系列终章，特效全面升级。', '吴京 / 刘德华 / 李雪健', 173, '呼和浩特·万达影城(万达广场店)'),
(1, '周杰伦嘉年华世界巡回演唱会', 1, '', '周杰伦"嘉年华"世界巡回演唱会呼和浩特站，歌迷期待已久的音乐盛宴，超强舞美与经典曲目联唱。', '周杰伦', 150, '呼和浩特·内蒙古体育馆'),
(1, '《天鹅湖》芭蕾舞剧', 1, '', '俄罗斯皇家芭蕾舞团经典之作《天鹅湖》，优美动人的芭蕾艺术与震撼配乐完美结合。', '俄罗斯皇家芭蕾舞团', 135, '呼和浩特·乌兰恰特大剧院');

-- 场次
INSERT INTO sessions (ticket_id, show_time, base_price, seat_rows, seat_cols) VALUES
(1, '2026-11-05 19:00:00', 45.00, 8, 10),
(1, '2026-11-06 14:30:00', 40.00, 8, 10),
(2, '2026-11-08 20:00:00', 380.00, 12, 14),
(2, '2026-11-09 19:30:00', 380.00, 12, 14),
(3, '2026-11-12 19:30:00', 280.00, 10, 12),
(3, '2026-11-13 19:30:00', 280.00, 10, 12);

-- ---------------------------------------------------------------------
-- 为每个场次生成座位（价格按行：前 1/3 排高档，中间中档，后排基础价）
-- 使用 MySQL 8 递归 CTE，纯 SQL 实现，无需存储过程
-- ---------------------------------------------------------------------
INSERT INTO seats (session_id, seat_row, seat_col, price)
WITH RECURSIVE
rowgen AS (SELECT 0 AS r UNION ALL SELECT r+1 FROM rowgen WHERE r < 11),
colgen AS (SELECT 1 AS c UNION ALL SELECT c+1 FROM colgen WHERE c < 14)
SELECT s.id,
       CHAR(65 + r) AS seat_row,
       c AS seat_col,
       ROUND(CASE
           WHEN r < 3 THEN s.base_price * 1.30
           WHEN r < s.seat_rows / 2 THEN s.base_price * 1.15
           ELSE s.base_price
       END, 2) AS price
FROM sessions s
JOIN rowgen ON r < s.seat_rows
JOIN colgen ON c <= s.seat_cols;

-- 随机预置一部分已售座位，便于演示选座效果
UPDATE seats SET status = 2
WHERE id IN (
    SELECT * FROM (SELECT id FROM seats WHERE session_id IN (1,3,5) ORDER BY RAND() LIMIT 40) t
);

SELECT '数据库初始化完成！' AS message;
