// 选座页交互逻辑
(function () {
  var selected = new Map(); // id -> {seat, price}
  var list = document.getElementById('selList');
  var btn = document.getElementById('btnConfirm');
  var countEl = document.getElementById('count');
  var totalEl = document.getElementById('total');

  // 绑定座位点击
  document.querySelectorAll('.seat').forEach(function (seat) {
    if (seat.classList.contains('sold') || seat.classList.contains('locked')) {
      return; // 已售/锁定不可选
    }
    seat.addEventListener('click', function () {
      var id = seat.dataset.id;
      if (selected.has(id)) {
        selected.delete(id);
        seat.classList.remove('selected');
      } else {
        // 限制最多选 6 张，避免误操作
        if (selected.size >= 6) { alert('单次最多选择 6 个座位'); return; }
        selected.set(id, { seat: seat.dataset.seat, price: parseFloat(seat.dataset.price) });
        seat.classList.add('selected');
      }
      render();
    });
  });

  function render() {
    list.innerHTML = '';
    var count = 0, total = 0;
    selected.forEach(function (v) {
      count++;
      total += v.price;
      var div = document.createElement('div');
      div.className = 'sl';
      div.innerHTML = '<span>' + v.seat + '</span><span>￥' + v.price.toFixed(2) + '</span>';
      list.appendChild(div);
    });
    if (count === 0) {
      list.innerHTML = '<div class="sl" style="color:#aaa;border:none;justify-content:center;">请选择座位</div>';
    }
    countEl.textContent = count;
    totalEl.textContent = '￥' + total.toFixed(2);
    btn.disabled = count === 0;
  }

  // 确认选座 -> 锁定座位并创建订单
  btn.addEventListener('click', function () {
    var seatIds = Array.from(selected.keys());
    btn.disabled = true;
    btn.textContent = '提交中...';
    fetch(window.API_BASE + '/api/lock_seats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: window.SESSION_ID, seat_ids: seatIds })
    }).then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.success) {
          window.location.href = window.API_BASE + '/order/' + res.order_id + '/confirm';
        } else {
          alert(res.msg);
          btn.disabled = false;
          btn.textContent = '确认选座';
        }
      })
      .catch(function () {
        alert('网络错误，请重试');
        btn.disabled = false;
        btn.textContent = '确认选座';
      });
  });
})();
