from pythonanywhere import waveAlgo
from flask import Flask, request, render_template, session, redirect
import logging.handlers
from kite_trade import *

logging.basicConfig(level=logging.INFO, filename="algo_log.log",filemode="a", format="%(message)s")
_logger = logging.getLogger('algo_log')

app = Flask(__name__, template_folder='.')

wv = waveAlgo()
@app.route('/', methods=("POST", "GET"))
def html_table():
    return render_template('sample_back.html', row_data=wv.tradebook.values.tolist(), algo_status=wv.algo_status)


@app.route("/connect")
def connect():
    return {"algo_status":wv.algo_status, "algo_mode": wv.kite_order}


@app.route('/clientEvent', methods=("POST", "GET"))
def algo_status():
    data = request.form.to_dict(flat=False)
    msg = data['algo_status'][0]
    if msg == "stop":
        _logger.info("Algo Stopped")
        wv.algo_status = False
        wv.tradebook.to_csv(wv.tradebook_path, index=False)
    else:
        _logger.info("Algo Started")
        wv.algo_status = True
    return "", 200


@app.route("/enctoken", methods=("POST", "GET"))
def token():
    data = request.form.to_dict(flat=False)
    msg = data['enctoken'][0]
    _logger.info(msg)
    wv.kite = KiteApp(enctoken=str(msg))
    return "", 200


@app.route('/liveMode', methods=("POST", "GET"))
def live_mode():
    data = request.form.to_dict(flat=False)
    msg = data['algo_mode'][0]
    if msg == "live":
        _logger.info("Switched to Live mode")
        wv.kite_order = True
    else:
        _logger.info("Switched to Paper mode")
        wv.kite_order = False
    return "", 200


@app.route('/exit_all')
def closePositions():
    _logger.info("Closed all position")
    wv.exit_all_position()
    return "", 200


@app.route('/message')
def data():
    profit = wv.actual_profit
    res = render_template('data.html', row_data=wv.tradebook[1:].sort_values(by=['unsubscribe', 'entry_time'],
                                                                             ascending=[False,
                                                                                        False]).values.tolist(),
                          profit=profit, balance=wv.balance)
    # time.sleep(1)
    return res


@app.route('/save')
def save():
    wv.tradebook.to_csv(wv.tradebook_path, index=False)
    return "", 200


if __name__ == "__main__":
    try:
        app.run(host='0.0.0.0')
    except KeyboardInterrupt:
        wv.tradebook.to_csv(wv.tradebook_path, index=False)
    finally:
        wv.tradebook.to_csv(wv.tradebook_path, index=False)