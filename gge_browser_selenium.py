from websocket_server import WebsocketServer

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from websockets.sync.client import connect

import json
import threading
import _thread
import sys
import traceback

def open_browser(game_url, on_ready):
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument("--start-maximized")
    options.add_argument("--allow-running-insecure-content")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)

    driver.get(game_url)
    iframe = start_game(driver, on_ready)
    threading.Thread(target=watch_reload, args=(driver, iframe, on_ready), daemon=True).start()

def start_game(webdriver, on_ready):
    webdriver.set_network_conditions(offline=True, latency=1000, throughput=0)
    webdriver.execute_cdp_cmd("Network.clearBrowserCache", {})
    webdriver.set_network_conditions(offline=False, latency=1000, throughput=500 * 1024)
    webdriver.refresh()
    wait = WebDriverWait(webdriver, 30, poll_frequency=0.01)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body[style*="background-image"]')))
    wait.until(EC.presence_of_element_located((By.ID, 'game')))
    iframe = webdriver.find_element(By.ID, 'game')
    webdriver.switch_to.frame(iframe)
    webdriver.execute_script(on_ready)
    webdriver.switch_to.default_content()
    webdriver.delete_network_conditions()
    return iframe

def watch_reload(webdriver, iframe, on_ready):
    while True:
        try:
            WebDriverWait(webdriver, float('inf')).until(EC.staleness_of(iframe))
            iframe = start_game(webdriver, on_ready)
        except Exception as e:
            if isinstance(e, WebDriverException) and "target frame detached" in str(e):
                pass
            elif isinstance(e, WebDriverException) and "unknown error: cannot determine loading status" in str(e):
                pass
            elif isinstance(e, WebDriverException) and "unknown error: bad inspector message" in str(e):
                pass
            else:
                traceback.print_exc()
                _thread.interrupt_main()
                sys.exit()

def get_server_version():
    with connect(f"wss://ep-live-mz-int1-sk1-gb1-game.goodgamestudios.com:443") as websocket:
        websocket.send("<msg t='sys'><body action='login' r='0'><login z='EmpireEx'><nick><![CDATA[]]></nick><pword><![CDATA[1113030%fr%0]]></pword></login></body></msg>")
        websocket.recv()
        websocket.recv()
        websocket.recv()
        websocket.send("%xt%EmpireEx%vck%1%1113030%web-html5%<RoundHouseKick>%4.153563674545914e+307%")
        message = websocket.recv()
        message = message.decode('utf-8').split('%')
        return message[5]

def connect_with_browser(ws_mock, game_url, ws_server_port):
    def on_server_message(ws, message):
        type, data = message.split('#', 1)
        if type == 'send' and ws_mock.on_send:
            ws_mock.on_send(ws_mock, data)
        elif type == 'open' and ws_mock.on_open:
            ws_mock.on_open(ws_mock)
        elif type == 'close' and ws_mock.on_close:
            close_data = json.loads(data)
            ws_mock.on_close(ws_mock, close_data.get('code', ''), close_data.get('reason', ''))
        elif type == 'error' and ws_mock.on_error:
            error_data = json.loads(data)
            ws_mock.on_error(ws_mock, error_data.get('message', ''))
        elif type == 'message' and ws_mock.on_message:
            ws_mock.on_message(ws_mock, data)
        elif type == 'log' and ws_mock.on_log:
            ws_mock.on_log(ws_mock, data)

    ws_mock.ws_server = WebsocketServer(ws_server_port,on_message=on_server_message)
    threading.Thread(target=ws_mock.ws_server.start_sync, daemon=True).start()

    server_version = get_server_version()

    on_ready = """
        const originalXMLHttpRequest = window.XMLHttpRequest;
        window.XMLHttpRequest = class extends originalXMLHttpRequest {
            open(method, url, async, user, password) {
                this.url = url;
                if (/config\/network\/[0-9]+\.xml/.test(url)) {
                    url = "https://raw.githubusercontent.com/danadum/ggs-assets/main/e4k/network.xml";
                }
                else if (url.startsWith('https://player-kv.public.ggs-ep.com/api/players')) {
                    url = url.replace(/players\/12-[0-9]+-/, `/players/16-${window.networkId}-`);
                }
                else if (url.startsWith('https://accounts.public.ggs-ep.com/players')) {
                    url = url.replace(/players\/12-[0-9]+-/, `/players/16-${window.networkId}-`);
                }
                else if (url.startsWith('https://gdpr-delete.public.ggs-ep.com/players')) {
                    url = url.replace(/players\/12-[0-9]+-/, `/players/16-${window.networkId}-`);
                }
                else if (url.startsWith('https://reward-hub.public.ggs-ep.com/api/rewards')) {
                    url = url.replace('/rewards/12', '/rewards/16');
                }

                super.open(method, url, async, user, password);
            }

            addEventListener(type, listener, options) {
                super.addEventListener(type, async () => {
                    if (type === 'readystatechange' && this.readyState === 4 && /items\/items_v[0-9]+\.[0-9]+\.json/.test(this.url)) {
                        let response = JSON.parse(this.response ?? this.responseText);
                        Object.defineProperty(this, 'response', {writable: true});
                        Object.defineProperty(this, 'responseText', {writable: true});
                        let request = new originalXMLHttpRequest();
                        request.open('GET', 'https://raw.githubusercontent.com/vanBrusselTechnologies/E4K-data/main/data/quests.json', false);
                        request.send();
                        let quests = JSON.parse(request.responseText, (key, value, data) => typeof value === 'number' ? data.source : value);
                        response.quests = quests.quest;
                        this.response = this.responseText = JSON.stringify(response);
                    }
                    else if (type === 'load' && this.readyState === 4 && /config\/languages\/[0-9]+\/[a-z_]+\.json/.test(this.url)) {
                        let response = JSON.parse(this.response ?? this.responseText);
                        Object.defineProperty(this, 'response', {writable: true});
                        Object.defineProperty(this, 'responseText', {writable: true});
                        let request = new originalXMLHttpRequest();
                        let lang = this.url.match(/config\/languages\/[0-9]+\/([a-z_]+)\.json/)[1];
                        request.open('GET', `https://langserv.public.ggs-ep.com/e4k/${lang}/*`, false)
                        request.send();
                        let e4kLang = JSON.parse(request.responseText);
                        response = {...response, ...e4kLang};
                        this.response = this.responseText = JSON.stringify(response);
                    }
                    listener();
                }, options);
            }
        };

        window.sockets = [];

        const localSocket = new WebSocket('ws://localhost:%i');
        localSocket.addEventListener('message', async (event) => {
            let data = await event.data;
            window.sockets.forEach(socket => socket.send(data));
        });

        const originalWebSocket = window.WebSocket;
        window.WebSocket = class extends originalWebSocket {
            constructor(url, protocols) {
                localSocket.send(`log#Original websocket url: ${url}`);             
                if (url.startsWith('wss://e4k-live')) {
                    url = url.replace('wss://', 'ws://').replace(':443', ':80');
                }
                localSocket.send(`log#Modified websocket url: ${url}`);

                super(url, protocols);
                window.sockets.push(this);

                this.addEventListener('open', event => {
                    localSocket.send(`open#`);
                });

                this.addEventListener('close', event => {
                    localSocket.send(`close#${JSON.stringify({code: event.code, reason: event.reason})}`);
                    window.sockets = window.sockets.filter(socket => socket !== this);
                });

                this.addEventListener('error', event => {
                    localSocket.send(`error#${JSON.stringify({message: event.data})}`);
                });

                Object.defineProperty(this, "onmessage", {
                    set(fn) {
                        this.original_onmessage = fn;
                        return this.addEventListener('message', async (event) => {
                            let data = await event.data.text();
                            data = data.split('%%');

                            if (data[2] === 'vpn') {
                                if (data[4] === '10005') data[4] = '0';
                                if (data[4] === '10021') data[4] = '22';
                                if (data[4] === '10022') data[4] = '28';
                                if (data[4] === '10023') data[4] = '70';
                            }
                            else if (data[2] === 'vln') {
                                if (data[4] === '10005') data[4] = '0';
                                if (data[4] === '10010') data[4] = '21';
                            }
                            else if (data[2] === 'core_lga') {
                                data[2] = 'lli';
                                if (data[4] === '10005') data[4] = '0';
                                if (data[4] === '10010') data[4] = '21';
                                if (data[4] === '10011') data[4] = '20';
                            }
                            else if (data[2] === 'core_reg') {
                                data[2] = 'lre';
                                if (data[4] === '10005') data[4] = '0';
                                if (data[4] === '10007') {
                                    data[4] = '3';
                                    data.splice(5, 1);
                                }
                            }
                            else if (data[2] === 'core_pol' && data[4] === '10005') {
                                let payload = JSON.parse(data[5]);
                                payload = payload.filter(offer => !offer.OD.some(dialog => dialog.visualComponents.some(component => component.name === 'offersHub')));
                                data[5] = JSON.stringify(payload);
                            }
                            else if (data[2] === 'core_gpi' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                window.networkId = payload.networkId;
                            }
                            else if (data[2] === 'sei' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                let blacksmith = payload.E.findIndex(e => e.EID === 92);
                                if (blacksmith !== -1) payload.E[blacksmith].EID = 116;
                                data[5] = JSON.stringify(payload);
                            }
                            else if (data[2] === 'gbd' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                if (!payload.mvf.AFS) payload.mvf.AFS = payload.mvf.AF;
                                if (!payload.sne) payload.sne = {MSG: []};
                                data[5] = JSON.stringify(payload);
                                this.send(`%%xt%%${this.serverKey}%%sne%%1%%{}%%`);
                                if (payload.gal?.AID && payload.gal?.AID !== -1) {
                                    this.send(`%%xt%%${this.serverKey}%%acl%%1%%{}%%`);
                                    this.send(`%%xt%%${this.serverKey}%%ain%%1%%{"AID": ${payload.gal.AID}}%%`);
                                }
                            }

                            data = data.join('%%');
                            event = new MessageEvent('message', {data: new Blob([data])});
                            localSocket.send(`message#${data}`);
                            fn(event);
                        });
                    }
                });
            }

            send(data) {
                if (data.includes("action='login'")) {
                    this.serverKey = new DOMParser().parseFromString(data, "application/xml").documentElement.firstChild.firstChild.getAttribute('z');
                }
                else if (data.includes('%%vck%%1%%')) {
                    localSocket.send(`send#${data}`);
                    data = "%%xt%%vck%%1%%0%%%s%%37.0.0%%";
                    this.dispatchEvent(new MessageEvent('message', {data: new Blob([data])}));
                    return;
                }
                else if (data.includes('%%lli%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    data = `%%xt%%${data[2]}%%core_lga%%1%%{"NM": "${payload.NOM}", "PW": "${payload.PW}", "L": "fr", "AID": "1674256959939529708", "DID": 5, "PLFID": "3", "ADID": "null", "AFUID": "appsFlyerUID", "IDFV": "null"}%%`;
                }
                else if (data.includes('%%lre%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    data = `%%xt%%${data[2]}%%core_reg%%1%%{"NM": "${payload.PN}", "PW": "${payload.PW}", "L": "fr", "AID": "1674256959939529708", "DID": 5, "PLFID": "3", "ADID": "null", "AFUID": "appsFlyerUID", "IDFV": "null"}%%`;
                }               
                else if (data.includes('%%sbp%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    if (payload.TID === 116) payload.TID = 92;
                    data[5] = JSON.stringify(payload);
                    data = data.join('%%');
                }
                localSocket.send(`send#${data}`);
                super.send(data);
            }
        };
    """ % (ws_server_port, server_version)

    open_browser(game_url, on_ready)
