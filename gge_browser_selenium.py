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
import time
import requests
import os
import urllib.parse
import base64

def open_browser(game_url, on_ready):
    port = 9222
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument(f"--user-data-dir={os.path.join(os.getcwd(), 'user-data')}")
    options.add_argument(f"--remote-debugging-port={port}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)

    driver.get(game_url)
    threading.Thread(target=watch_reload, args=(driver, on_ready), daemon=True).start()
    threading.Thread(target=watch_webshop, args=(driver,), daemon=True).start()
    threading.Thread(target=watch_new_tab, args=(on_ready, port), daemon=True).start()

def watch_new_tab(on_ready, port):
    while True:
        try:
            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", f"localhost:{port}")
            driver = webdriver.Chrome(options=options)
            window_handles = set(driver.window_handles)

            WebDriverWait(driver, float('inf')).until(EC.any_of(EC.number_of_windows_to_be(len(window_handles) + 1), EC.number_of_windows_to_be(len(window_handles) - 1)))
            if len(driver.window_handles) <= len(window_handles):
                continue
            driver.switch_to.window(next(iter(set(driver.window_handles) - window_handles)))
            threading.Thread(target=watch_reload, args=(driver, on_ready), daemon=True).start()
            threading.Thread(target=watch_webshop, args=(driver,), daemon=True).start()
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

def start_game(webdriver, on_ready):
    webdriver.set_network_conditions(offline=True, latency=1000, throughput=0)
    webdriver.execute_cdp_cmd("Network.clearBrowserCache", {})
    webdriver.set_network_conditions(offline=False, latency=1000, throughput=500 * 1024)
    webdriver.refresh()
    wait = WebDriverWait(webdriver, 30, poll_frequency=0.01)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body[style*="background-image"]')))
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe#game')))
    iframe = webdriver.find_element(By.CSS_SELECTOR, 'iframe#game')
    webdriver.switch_to.frame(iframe)
    webdriver.execute_script(on_ready)
    webdriver.switch_to.default_content()
    webdriver.delete_network_conditions()
    return iframe

def watch_webshop(webdriver):
    wait = WebDriverWait(webdriver, float('inf'))
    while True:
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe#dialog[src^="https://canvas.goodgamestudios.com"]')))
            iframe = webdriver.find_element(By.CSS_SELECTOR, 'iframe#dialog[src^="https://canvas.goodgamestudios.com"]')
            url, args = iframe.get_attribute('src').split('?', 1)
            args = {k: v for k, v in (arg.split('=', 1) for arg in args.split('&'))}
            r = requests.get(urllib.parse.unquote(args['lemonstand.customization.url'].replace('em.json', 'mbs.json')))
            customization = r.json()
            customization['categories']['vouchers']['enabled'] = True
            customization['platformContext']['storeIntegrationType'] = "embedded"
            args['lemonstand.customization.url'] = f"data:text/json;base64,{base64.b64encode(json.dumps(customization).encode()).decode()}"
            url = f"{url}?locale={args['locale']}&zoneId={args['zoneId']}&criteria={args['criteria']}&lemonstand.customization.url={args['lemonstand.customization.url']}"
            
            gameframe = webdriver.find_element(By.CSS_SELECTOR, 'iframe#game')
            webdriver.switch_to.frame(gameframe)
            network_id, server_id, player_id = webdriver.execute_script("return [window.networkId, window.serverId, window.playerId]")
            webdriver.switch_to.default_content()

            r = requests.get(f"https://accounts.public.ggs-ep.com/players/16-{network_id}-{server_id}-{player_id}/gnip-phrase", headers={"Authorization": f"Bearer {args['token']}"})
            accound_id = r.json()['gnipPhrase']
            r = requests.post("https://mbs-accounts.goodgamestudios.com/login/lemonstand", allow_redirects=False, headers={"content-type": "application/x-www-form-urlencoded", "origin": "https://e4k.goodgamestudios.com"}, data={"gnipPhrase": accound_id, "errorUrl": "https://e4k.goodgamestudios.com"})
            cookies = r.headers['set-cookie'].split(', ')
            
            webdriver.switch_to.frame(iframe)
            for cookie in cookies:
                data, args = cookie.split('; ', 1)
                name, value = data.split('=', 1)
                args = {part[0]: part[1] if len(part) > 1 else None for part in (arg.split('=', 1) for arg in args.split('; '))}
                webdriver.add_cookie({'name': name, 'value': value, "expiry": int(time.time()) + int(args['Max-Age']), "domain": args["Domain"], "path": args['Path'], "secure": 'Secure' in args, "sameSite": "None"})
            webdriver.switch_to.default_content()

            webdriver.execute_script(f"arguments[0].src = '{url}'", iframe)
            wait.until(EC.staleness_of(iframe))
        except Exception as e:
            if isinstance(e, WebDriverException) and "target frame detached" in str(e):
                pass
            elif isinstance(e, WebDriverException) and "unknown error: cannot determine loading status" in str(e):
                pass
            elif isinstance(e, WebDriverException) and "unknown error: bad inspector message" in str(e):
                pass
            else:
                traceback.print_exc()
                break

def watch_reload(webdriver, on_ready):
    while True:
        try:
            WebDriverWait(webdriver, float('inf')).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe#game')))
            iframe = start_game(webdriver, on_ready)
            WebDriverWait(webdriver, float('inf')).until(EC.staleness_of(iframe))
        except Exception as e:
            if isinstance(e, WebDriverException) and "target frame detached" in str(e):
                pass
            elif isinstance(e, WebDriverException) and "unknown error: cannot determine loading status" in str(e):
                pass
            elif isinstance(e, WebDriverException) and "unknown error: bad inspector message" in str(e):
                pass
            else:
                traceback.print_exc()
                break

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

    ws_mock.ws_server = WebsocketServer(ws_server_port, on_message=on_server_message)
    threading.Thread(target=ws_mock.ws_server.start_sync, daemon=True).start()

    server_version = get_server_version()

    on_ready = """
        function getE4KData(file) {
            let request = new XMLHttpRequest();
            request.open('GET', `https://raw.githubusercontent.com/vanBrusselTechnologies/E4K-data/main/data/${file}.json`, false);
            request.send();
            return JSON.parse(request.responseText, (key, value, data) => typeof value === 'number' && key !== 'wodID' && key !== 'minLevel' ? data.source : typeof value === 'string' ? value.replaceAll('&amp;', '&') : value);
        }

        const originalXMLHttpRequest = window.XMLHttpRequest;
        window.XMLHttpRequest = class extends originalXMLHttpRequest {
            open(method, url, async, user, password) {
                this.url = url;
                if (/config\/network\/[0-9]+\.xml/.test(url)) {
                    url = "https://raw.githubusercontent.com/danadum/ggs-assets/main/e4k/network.xml";
                }
                else if (url.startsWith('https://player-kv.public.ggs-ep.com/api/players')) {
                    url = url.replace(/\/players\/12-[0-9]+-[0-9]+-/, `/players/16-${window.networkId}-${window.serverId}-`);
                }
                else if (url.startsWith('https://accounts.public.ggs-ep.com/players')) {
                    url = "https://cors-buster.fly.dev/" + url.replace(/\/players\/12-[0-9]+-[0-9]+-/, `/players/16-${window.networkId}-${window.serverId}-`);
                }
                else if (url.startsWith('https://gdpr-delete.public.ggs-ep.com/players')) {
                    url = url.replace(/\/players\/12-[0-9]+-[0-9]+-/, `/players/16-${window.networkId}-${window.serverId}-`);
                }
                else if (url.startsWith('https://reward-hub.public.ggs-ep.com/api/rewards')) {
                    url = url.replace(/\/rewards\/12-[0-9]+-[0-9]+-/, `/rewards/16-${window.networkId}-${window.serverId}-`);
                }

                super.open(method, url, async, user, password);
            }

            addEventListener(type, listener, options) {
                super.addEventListener(type, async () => {
                    if (type === 'readystatechange' && this.readyState === 4 && /items\/items_v[0-9]+\.[0-9]+\.json/.test(this.url)) {
                        let response = JSON.parse(this.response ?? this.responseText);
                        Object.defineProperty(this, 'response', {writable: true});
                        Object.defineProperty(this, 'responseText', {writable: true});

                        response.quests = getE4KData('quests').quest;
                        response.achievements = getE4KData('achievements').achievement;
                        response.crestsymbols = getE4KData('crestsymbols').crestsymbol;
                        response.subscriptionsBuffs = getE4KData('subscriptionsBuffs').subscriptionsBuff;
                        response.rewards = getE4KData('rewards').reward;
                        response.tempServerRankRewards = getE4KData('tempServerRankRewards').tempServerRankReward;
                        response.allianceBattleGroundRankRewards = getE4KData('allianceBattleGroundRankRewards').allianceBattleGroundRankReward;
                        response.leaguetypeevents = getE4KData('leaguetypeEvents').leaguetypeevent;
                        response.sceatSkills = getE4KData('sceatSkills').sceatSkill;
                        response.sceatSkillTiers = getE4KData('sceatSkillTiers').sceatSkillTier;

                        let data = getE4KData('effects').effect;
                        response.effects = response.effects.filter(effect => !data.some(e => e.effectID === effect.effectID)).concat(data);
                        data = getE4KData('buildings').building;
                        data = data.map(building => {
                            if (building.wodID === 1506) building.wodID = building.crossplayID = 1508;
                            if (building.wodID === 1654) building.wodID = building.crossplayID = 1506;
                            return building;
                        });
                        data = data.map(building => ({...building, type: response.buildings.find(b => b.wodID === +(building.crossplayID ?? building.wodID))?.type ?? building.type}));
                        window.buildings = response.buildings = response.buildings.filter(building => building.wodID !== 1506 && !data.some(b => b.wodID === building.wodID)).concat(data);
                        data = getE4KData('units').unit;
                        response.units = response.units.map(unit => ({...data.find(u => +u.crossplayID === unit.wodID) ?? unit, type: unit.type}));
                        data = getE4KData('equipment_effects').equipment_effect;
                        response.equipment_effects = response.equipment_effects.map(effect => data.find(e => e.crossplayID === effect.equipmentEffectID) ?? effect);
                        data = getE4KData('equipments').equipment;
                        response.equipments = response.equipments.map(equipment => data.find(e => e.crossplayID === equipment.equipmentID) ?? equipment);
                        data = getE4KData('researches').research.filter(research => research.crossplayID || !research.unwalkable);
                        response.researches = data.map(research => !research.x ? research : ({...research, ...(({x, y, ...rest}) => ({x, y}))(response.researches.find(r => r.researchID === research.crossplayID) ?? {y: 6})})).filter(research => !(research.y > 5));

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
                        response = {...response, ...e4kLang, ...Object.fromEntries(Object.entries(response).filter(([key]) => key.startsWith('dialog_alliance_rank')))};
                        this.response = this.responseText = JSON.stringify(response);
                    }
                    else if (type === 'readystatechange' &&  this.readyState === 4 && /Crest\/CastleCrestSymbols\/CastleCrestSymbols--[0-9]*.js$/.test(this.url)) {
                        let response = this.response ?? this.responseText;
                            Object.defineProperty(this, 'response', {writable: true});
                        Object.defineProperty(this, 'responseText', {writable: true});
                        for (let i = 99; i > 38; i--) {
                            response = response.replaceAll(`extCrestSymbol_${i}`, `extCrestSymbol_${i + 1}`);
                        }
                        this.response = this.responseText = response;
                        window.crests = this.response;
                    }
                    listener();
                }, options);
            }
        };

        window.sockets = [];

        const localSocket = window.localSocket = new WebSocket('ws://localhost:%i');
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
                            data = data.replaceAll(/&#(\d+);/g, "&$1;");
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
                                if (data[4] === '10007') data[4] = '3';
                                if (data[4] === '10018') data[4] = '24';
                                if (data[4] === '10019') data[4] = '23';
                                if (data[4] === '10021') data[4] = '22';
                                if (data[4] === '10022') data[4] = '28';
                                if (data[4] === '10023') data[4] = '70';
                            }
                            else if (data[2] === 'tse' && data[4] === '0') {
                                this.dispatchEvent(new MessageEvent('message', {data: new Blob(["%%xt%%lli%%1%%0%%"])}));
                            }
                            else if (data[2] === 'core_avl' && data[4] === '10005') {
                                let payload = JSON.parse(data[5]);
                                payload = {LT: payload.P};
                                data[5] = JSON.stringify(payload);
                                data[4] = '0';
                                data[2] = 'slt';
                            }
                            else if (data[2] === 'core_pol' && data[4] === '10005') {
                                let payload = JSON.parse(data[5]);
                                for (let offer of payload) {
                                    for (let dialog of offer.OD) {
                                        for (let component of dialog.visualComponents ?? []) {
                                            if (component.name === 'offersHub') {
                                                dialog.visualComponents = dialog.visualComponents.filter(c => c !== component);
                                                if (dialog.visualComponents.some(c => c.name === 'offerDialog' && c.params.DN === 'BestsellerShopDialog' && c.params.AS === false)) {
                                                    dialog.visualComponents.push({"name": "interfaceButton", "params": {"BT": "Btn_BestsellerShop", "PT": 6, "TID": "dialog_privateBestsellerShop_title"}});
                                                }
                                                else if (dialog.visualComponents.some(c => c.name === 'offerDialog' && c.params.DN === 'BestsellerShopDialog' && c.params.AS === true)) {}
                                                else if (offer.OD.length > 1) {
                                                    dialog.visualComponents.push({"name": "failedDialog","params": {"AS": true,"OS": [443,423],"DN": "CastlePOWhaleChestFinishExternal"}},{"name": "finishDialog","params": {"AS": true,"DN": "CastlePOStandardOKExternal"}},{"name": "questDialog","params": {"AS": false,"DN": "CastlePOMultiChest"}},{"name": "offerDialog","params": {"AS": false,"DN": "CastlePOMultiChest","DC": {"BAB": 1,"OT": 1,"CID": "dialog_privateOffer_whaleChest_descripton1"}}},{"name": "interfaceButton","params": {"BT": "Btn_POMultiChest","OS": true,"PT": 6,"TID": "dialog_primeday_specialoffer_title"}});
                                                }
                                                else if (offer.QD?.conditions?.some(condition => condition.name === 'cashOfferPackage')) {}
                                                else {
                                                    dialog.visualComponents.push({"name": "finishDialog","params": {"AS": true,"OS": [423,443],"DN": "CastlePaymentRewardSpecialOfferFinish"}},{"name": "questDialog","params": {"AS": false,"DN": "CastlePrivatePrimeDayDynamicDialog","DC": {"HL": [],"LEID": {"TXT": {"TXT1": {"A": [250],"ID": "dialog_specialOffer_bonus_1"},"TXT0": {"A": [2000000],"ID": "dialog_specialOffer_bonus_0"}},"ID": -1,"ICON": "icon_hc_rubi_rm"},"REID": {"TXT": {"TXT0": {"A": [],"ID": "dialog_specialOffer_limitedTime"}},"ID": -1},"ID": "fullScreenOfferDC","RM": {"A": [19000],"T": 0},"TSID": 42,"TID": "dialog_specialOffer_title_1","SID": 1}}},{"name": "interfaceButton","params": {"BT": "Btn_POMultiChest","OS": true,"PT": 6,"TID": "dialog_primeday_specialoffer_title"}});
                                                }
                                            }
                                        }
                                    }
                                }
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
                                window.playerId = payload.gpi.PID;
                            }
                            else if ((data[2] === 'jaa' || data[2] === 'ebe') && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                payload.gca.BD = payload.gca.BD.map(building => {
                                    let b = window.buildings.find(b => b.wodID === building[0]);
                                    building[9] = b && Object.keys(b).some(key => key.endsWith('production')) ? ~~(building[9] * 100) : -1;
                                    return building;
                                });
                                payload.gca.T = payload.gca.T.map(building => (building[9] = -1, building));
                                payload.gca.FP = payload.gca.FP?.map(building => (building[9] = -1, building));
                                data[5] = JSON.stringify(payload);
                            }
                            else if (data[2] === 'gcb' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                payload.B = payload.B.map(building => {
                                    let b = window.buildings.find(b => b.wodID === building[0]);
                                    building[9] = b && Object.keys(b).some(key => key.endsWith('production')) ? ~~(building[9] * 100) : -1;
                                    return building;
                                });
                                data[5] = JSON.stringify(payload);
                            }
                            else if (data[2] === 'ego' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                let b = window.buildings.find(b => b.wodID === payload.O[0]);
                                payload.O[9] = b && Object.keys(b).some(key => key.endsWith('production')) ? ~~(payload.O[9] * 100) : -1;
                                data[5] = JSON.stringify(payload);
                            }
                            else if (data[2] === 'ams' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                if (payload.MIDS) {
                                    payload.MID = payload.MIDS[0];
                                    delete payload.MIDS;
                                }
                                data[5] = JSON.stringify(payload);
                            }
                            else if (data[2] === 'gas' && data[4] === '0') {
                                let payload = JSON.parse(data[5]);
                                payload.S = payload.S.map(s => {
                                    let army = JSON.parse(s.A);
                                    army = [army[1][0], army[0][0], army[2][0], army[1][1], army[0][1], army[2][1]]
                                    army = army.map(x => x?.filter((y, i) => i %% 3 !== 0));
                                    s.A = JSON.stringify(army);
                                    return s;
                                });
                                data[5] = JSON.stringify(payload);
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
                data = data.replaceAll(/&(\d+);/g, "&#$1;");

                if (data.includes("action='login'")) {
                    this.serverKey = new DOMParser().parseFromString(data, "application/xml").documentElement.firstChild.firstChild.getAttribute('z');
                    window.serverId = +(this.serverKey.split('_')?.[1] ?? 1);
                }
                else if (data.includes('%%vck%%1%%')) {
                    localSocket.send(`send#${data}`);
                    data = "%%xt%%vck%%1%%0%%%s%%37.0.0%%";
                    this.dispatchEvent(new MessageEvent('message', {data: new Blob([data])}));
                    return;
                }
                else if (data.includes('%%pin%%1%%')) {
                    data = data.split('%%');
                    data[3] = 'pinpon';
                    data[5] = JSON.stringify({});
                    data = data.join('%%');
                }
                else if (data.includes('%%lli%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    if (payload.LT) {
                        payload.PW = payload.LT;
                    }
                    else if (payload.PL) {
                        let d = data.slice();
                        let p = {LN: payload.NOM, P: payload.PW};
                        d[5] = JSON.stringify(p);
                        d[3] = 'core_avl';
                        d = d.join('%%');
                        this.send(d);
                    }
                    payload = {NM: payload.NOM, PW: payload.PW, L: payload.LANG, AID: payload.AID, DID: payload.DID, PLFID: payload.PLFID, ADID: "null", AFUID: "appsFlyerUID", IDFV: null};
                    data[5] = JSON.stringify(payload);
                    data[3] = 'core_lga';
                    data = data.join('%%');
                }
                else if (data.includes('%%lre%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    payload = {PN: payload.PN, PW: payload.PW, MAIL: `${payload.PN}@mail.com`, LANG: payload.LANG, AID: payload.AID, DID: payload.DID, PLFID: payload.PLFID, ADID: "null", AFUID: "appsFlyerUID", IDFV: null, REF: ""};
                    data[5] = JSON.stringify(payload);
                    data[3] = 'core_reg';
                    data = data.join('%%');
                    this.send(data);

                    data = data.split('%%');
                    payload = {NM: payload.PN, PW: payload.PW, L: payload.LANG, AID: payload.AID, DID: payload.DID, PLFID: payload.PLFID, ADID: payload.ADID, AFUID: payload.AFUID, IDFV: payload.IDFV};
                    data[5] = JSON.stringify(payload);
                    data[3] = 'core_lga';
                    data = data.join('%%');
                    this.send(data);

                    data = data.split('%%');
                    payload = {LN: payload.NM, P: payload.PW};
                    data[5] = JSON.stringify(payload);
                    data[3] = 'core_avl';
                    data = data.join('%%');
                }               
                else if (data.includes('%%sbp%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    if (payload.TID === 116) payload.TID = 92;
                    else if (payload.TID === 80) payload.TID = 107;
                    data[5] = JSON.stringify(payload);
                    data = data.join('%%');
                }
                else if (data.includes('%%ams%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    payload.MIDS = [payload.MID];
                    delete payload.MID;
                    data[5] = JSON.stringify(payload);
                    data = data.join('%%');
                }
                else if (data.includes('%%sas%%1%%')) {
                    data = data.split('%%');
                    let payload = JSON.parse(data[5]);
                    let army = JSON.parse(payload.A);
                    army = army.map(x => x.flatMap((y, i) => i %% 2 === 0 ? [~~(i / 2), y] : [y]));
                    army = [[army[1], army[4]], [army[0], army[3]], [army[2], army[5]]]
                    payload.A = JSON.stringify(army);
                    data[5] = JSON.stringify(payload);
                    data = data.join('%%');
                }

                localSocket.send(`send#${data}`);
                super.send(data);
            }
        };
    """ % (ws_server_port, server_version)

    open_browser(game_url, on_ready)
