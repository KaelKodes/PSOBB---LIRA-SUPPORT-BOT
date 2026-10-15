// Injected into Lira's psobb.exe only. Feeds that process synthetic
// keyboard and mouse state so it can be played while another client
// is the foreground window.
#define WIN32_LEAN_AND_MEAN
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

static const GUID GUID_SysKeyboard = {0x6F1D2B61, 0xD5A0, 0x11CF, {0xBF, 0xC7, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00}};
static const GUID GUID_SysMouse = {0x6F1D2B60, 0xD5A0, 0x11CF, {0xBF, 0xC7, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00}};
static const GUID IID_IDirectInput8A = {0xBF798030, 0x483A, 0x4DA2, {0xAA, 0x99, 0x5D, 0x64, 0xED, 0x36, 0x97, 0x00}};

static volatile LONG g_force[256];
static volatile LONG g_dx;
static volatile LONG g_dy;
static volatile LONG g_mbtn[4];
static volatile LONG g_stateCalls;
static volatile LONG g_dataCalls;
static volatile LONG g_acquireCalls;
static HWND g_hwnd;
static BYTE g_vkToDik[256];
static BYTE g_sentDik[256];
static SHORT(WINAPI* g_realAsync)(int);
static BOOL(WINAPI* g_realKeyboard)(PBYTE);
static HWND(WINAPI* g_realForeground)();
static HWND(WINAPI* g_realActive)();
static HANDLE g_log;
static HINSTANCE g_inst;

static void log_line(const char* text) {
    if (!g_log) return;
    DWORD n = (DWORD)strlen(text);
    WriteFile(g_log, text, n, &n, NULL);
    WriteFile(g_log, "\r\n", 2, &n, NULL);
}

static bool background() {
    HWND fg = g_realForeground ? g_realForeground() : GetForegroundWindow();
    if (!fg) return true;
    DWORD pid = 0;
    GetWindowThreadProcessId(fg, &pid);
    return pid != GetCurrentProcessId();
}

static HWND WINAPI HookGetForegroundWindow() {
    if (g_hwnd) return g_hwnd;
    return g_realForeground ? g_realForeground() : NULL;
}

static HWND WINAPI HookGetActiveWindow() {
    if (g_hwnd) return g_hwnd;
    return g_realActive ? g_realActive() : NULL;
}

static void init_map() {
    const char* row1 = "QWERTYUIOP";
    BYTE d = 0x10;
    for (int i = 0; row1[i]; i++) g_vkToDik[(BYTE)row1[i]] = d++;
    const char* row2 = "ASDFGHJKL";
    d = 0x1E;
    for (int i = 0; row2[i]; i++) g_vkToDik[(BYTE)row2[i]] = d++;
    const char* row3 = "ZXCVBNM";
    d = 0x2C;
    for (int i = 0; row3[i]; i++) g_vkToDik[(BYTE)row3[i]] = d++;
    g_vkToDik[VK_SPACE] = 0x39;
    g_vkToDik[VK_RETURN] = 0x1C;
    g_vkToDik[VK_ESCAPE] = 0x01;
    g_vkToDik[VK_TAB] = 0x0F;
    g_vkToDik[VK_SHIFT] = 0x2A;
    g_vkToDik[VK_LSHIFT] = 0x2A;
    g_vkToDik[VK_RSHIFT] = 0x36;
    g_vkToDik[VK_CONTROL] = 0x1D;
    g_vkToDik[VK_LCONTROL] = 0x1D;
    g_vkToDik[VK_RCONTROL] = 0x9D;
    g_vkToDik[VK_MENU] = 0x38;
    g_vkToDik[VK_LMENU] = 0x38;
    g_vkToDik[VK_RMENU] = 0xB8;
    g_vkToDik[VK_UP] = 0xC8;
    g_vkToDik[VK_DOWN] = 0xD0;
    g_vkToDik[VK_LEFT] = 0xCB;
    g_vkToDik[VK_RIGHT] = 0xCD;
    g_vkToDik[VK_BACK] = 0x0E;
    g_vkToDik[VK_HOME] = 0xC7;
    g_vkToDik[VK_END] = 0xCF;
    g_vkToDik[VK_PRIOR] = 0xC9;
    g_vkToDik[VK_NEXT] = 0xD1;
    g_vkToDik[VK_INSERT] = 0xD2;
    g_vkToDik[VK_DELETE] = 0xD3;
    for (int i = 1; i <= 9; i++) g_vkToDik['0' + i] = (BYTE)(0x01 + i);
    g_vkToDik['0'] = 0x0B;
    for (int i = 0; i < 10; i++) g_vkToDik[VK_F1 + i] = (BYTE)(0x3B + i);
    g_vkToDik[VK_F11] = 0x57;
    g_vkToDik[VK_F12] = 0x58;
}

static void apply_keyboard(BYTE* data) {
    for (int vk = 0; vk < 256; vk++) {
        if (!g_force[vk]) continue;
        BYTE dik = g_vkToDik[vk];
        if (dik) data[dik] |= 0x80;
    }
}

struct Slot {
    void** entry;
    void* orig;
};

static Slot g_acquire[4];
static Slot g_state[4];
static Slot g_data[4];
static int g_nacquire;
static int g_nstate;
static int g_ndata;

static void* find_orig(Slot* slots, int n, void* self, int index) {
    void** vt = *(void***)self;
    void** entry = &vt[index];
    for (int i = 0; i < n; i++) {
        if (slots[i].entry == entry) return slots[i].orig;
    }
    return NULL;
}

typedef HRESULT(STDMETHODCALLTYPE* Acquire_t)(void* self);
typedef HRESULT(STDMETHODCALLTYPE* GetDeviceState_t)(void* self, DWORD cb, void* data);
typedef HRESULT(STDMETHODCALLTYPE* GetDeviceData_t)(void* self, DWORD cb, void* data, DWORD* inout, DWORD flags);

static HRESULT STDMETHODCALLTYPE HookAcquire(void* self) {
    InterlockedIncrement(&g_acquireCalls);
    Acquire_t orig = (Acquire_t)find_orig(g_acquire, g_nacquire, self, 7);
    HRESULT hr = orig ? orig(self) : 0;
    if (FAILED(hr) && background()) return 0;
    return hr;
}

static HRESULT STDMETHODCALLTYPE HookGetDeviceState(void* self, DWORD cb, void* data) {
    InterlockedIncrement(&g_stateCalls);
    GetDeviceState_t orig = (GetDeviceState_t)find_orig(g_state, g_nstate, self, 9);
    HRESULT hr = orig ? orig(self, cb, data) : 0;
    bool back = background();
    if (cb == 256 && data) {
        if (back) {
            memset(data, 0, 256);
            hr = 0;
        }
        apply_keyboard((BYTE*)data);
        return hr;
    }
    if ((cb == 16 || cb == 20) && data) {
        if (back) {
            memset(data, 0, cb);
            hr = 0;
        }
        LONG* axes = (LONG*)data;
        axes[0] += InterlockedExchange(&g_dx, 0);
        axes[1] += InterlockedExchange(&g_dy, 0);
        BYTE* buttons = (BYTE*)data + 12;
        int nbtn = (cb - 12) > 4 ? 4 : (int)(cb - 12);
        for (int i = 0; i < nbtn; i++) {
            if (g_mbtn[i]) buttons[i] = 0x80;
            else if (back) buttons[i] = 0;
        }
        return hr;
    }
    return hr;
}

static HRESULT STDMETHODCALLTYPE HookGetDeviceData(void* self, DWORD cb, void* data, DWORD* inout, DWORD flags) {
    InterlockedIncrement(&g_dataCalls);
    GetDeviceData_t orig = (GetDeviceData_t)find_orig(g_data, g_ndata, self, 10);
    if (!orig) return 0x80004001L;
    if (!inout || (cb != 16 && cb != 20)) return orig(self, cb, data, inout, flags);
    if (!background()) return orig(self, cb, data, inout, flags);

    BYTE trash[20 * 16];
    DWORD flush = 16;
    orig(self, cb, trash, &flush, 0);

    if (!data) {
        *inout = 0;
        return 0;
    }
    DWORD cap = *inout;
    DWORD written = 0;
    BYTE* out = (BYTE*)data;
    DWORD now = GetTickCount();
    for (int vk = 0; vk < 256 && written < cap; vk++) {
        BYTE dik = g_vkToDik[vk];
        if (!dik) continue;
        BYTE down = g_force[vk] ? 1 : 0;
        if (down == g_sentDik[dik]) continue;
        g_sentDik[dik] = down;
        BYTE* ev = out + written * cb;
        memset(ev, 0, cb);
        *(DWORD*)(ev + 0) = dik;
        *(DWORD*)(ev + 4) = down ? 0x80 : 0;
        *(DWORD*)(ev + 8) = now;
        *(DWORD*)(ev + 12) = written + 1;
        written++;
    }
    *inout = written;
    return 0;
}

static void patch_slot(Slot* slots, int* count, int cap, void** entry, void* hook) {
    if (*count >= cap) return;
    if (*entry == hook) return;
    for (int i = 0; i < *count; i++) {
        if (slots[i].entry == entry) return;
    }
    DWORD old = 0;
    VirtualProtect(entry, sizeof(void*), PAGE_EXECUTE_READWRITE, &old);
    slots[*count].entry = entry;
    slots[*count].orig = *entry;
    (*count)++;
    *entry = hook;
    DWORD ignored = 0;
    VirtualProtect(entry, sizeof(void*), old, &ignored);
}

static void hook_device(void* device) {
    void** vt = *(void***)device;
    patch_slot(g_acquire, &g_nacquire, 4, &vt[7], (void*)HookAcquire);
    patch_slot(g_state, &g_nstate, 4, &vt[9], (void*)HookGetDeviceState);
    patch_slot(g_data, &g_ndata, 4, &vt[10], (void*)HookGetDeviceData);
}

static void hook_directinput() {
    HMODULE dinput = LoadLibraryA("dinput8.dll");
    if (!dinput) {
        log_line("dinput8 missing");
        return;
    }
    typedef HRESULT(WINAPI* Create_t)(HINSTANCE, DWORD, REFIID, void**, void*);
    Create_t create = (Create_t)GetProcAddress(dinput, "DirectInput8Create");
    if (!create) {
        log_line("DirectInput8Create missing");
        return;
    }
    void* di = NULL;
    HRESULT hr = create(GetModuleHandle(NULL), 0x0800, IID_IDirectInput8A, &di, NULL);
    if (FAILED(hr) || !di) {
        char buf[80];
        sprintf(buf, "DirectInput8Create failed %08lx", (unsigned long)hr);
        log_line(buf);
        return;
    }
    typedef HRESULT(STDMETHODCALLTYPE* CreateDevice_t)(void*, const GUID*, void**, void*);
    typedef ULONG(STDMETHODCALLTYPE* Release_t)(void*);
    void** diVt = *(void***)di;
    CreateDevice_t createDevice = (CreateDevice_t)diVt[3];
    Release_t release = (Release_t)diVt[2];
    const GUID* guids[2] = {&GUID_SysKeyboard, &GUID_SysMouse};
    const char* names[2] = {"keyboard", "mouse"};
    for (int i = 0; i < 2; i++) {
        void* dev = NULL;
        HRESULT dhr = createDevice(di, guids[i], &dev, NULL);
        if (FAILED(dhr) || !dev) {
            char buf[80];
            sprintf(buf, "CreateDevice %s failed %08lx", names[i], (unsigned long)dhr);
            log_line(buf);
            continue;
        }
        hook_device(dev);
        void** vt = *(void***)dev;
        Release_t devRelease = (Release_t)vt[2];
        devRelease(dev);
        char buf[64];
        sprintf(buf, "hooked %s", names[i]);
        log_line(buf);
    }
    release(di);
}

static SHORT WINAPI HookGetAsyncKeyState(int vk) {
    if (vk >= 0 && vk < 256 && g_force[vk]) return (SHORT)0x8001;
    if (background()) return 0;
    return g_realAsync ? g_realAsync(vk) : 0;
}

static BOOL WINAPI HookGetKeyboardState(PBYTE state) {
    BOOL ok = g_realKeyboard ? g_realKeyboard(state) : FALSE;
    if (!state) return ok;
    if (background() || !ok) memset(state, 0, 256);
    for (int i = 0; i < 256; i++) {
        if (g_force[i]) state[i] |= 0x80;
    }
    return TRUE;
}

static void patch_ptr(void** slot, void* value) {
    DWORD old = 0;
    VirtualProtect(slot, sizeof(void*), PAGE_EXECUTE_READWRITE, &old);
    *slot = value;
    DWORD ignored = 0;
    VirtualProtect(slot, sizeof(void*), old, &ignored);
}

static void patch_iat(HMODULE mod) {
    if (!mod) return;
    BYTE* base = (BYTE*)mod;
    IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return;
    IMAGE_NT_HEADERS* nt = (IMAGE_NT_HEADERS*)(base + dos->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return;
    IMAGE_IMPORT_DESCRIPTOR* imp = (IMAGE_IMPORT_DESCRIPTOR*)(base + dir.VirtualAddress);
    for (; imp->Name; imp++) {
        const char* dll = (const char*)(base + imp->Name);
        if (_stricmp(dll, "USER32.dll") != 0 && _stricmp(dll, "user32.dll") != 0) continue;
        IMAGE_THUNK_DATA* thunk = (IMAGE_THUNK_DATA*)(base + imp->FirstThunk);
        IMAGE_THUNK_DATA* orig = (IMAGE_THUNK_DATA*)(base + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        for (; orig->u1.AddressOfData; orig++, thunk++) {
            if (IMAGE_SNAP_BY_ORDINAL(orig->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME* name = (IMAGE_IMPORT_BY_NAME*)(base + orig->u1.AddressOfData);
            if (strcmp((char*)name->Name, "GetAsyncKeyState") == 0) {
                patch_ptr((void**)&thunk->u1.Function, (void*)HookGetAsyncKeyState);
                log_line("iat GetAsyncKeyState");
            } else if (strcmp((char*)name->Name, "GetKeyboardState") == 0) {
                patch_ptr((void**)&thunk->u1.Function, (void*)HookGetKeyboardState);
                log_line("iat GetKeyboardState");
            } else if (strcmp((char*)name->Name, "GetForegroundWindow") == 0) {
                patch_ptr((void**)&thunk->u1.Function, (void*)HookGetForegroundWindow);
                log_line("iat GetForegroundWindow");
            } else if (strcmp((char*)name->Name, "GetActiveWindow") == 0) {
                patch_ptr((void**)&thunk->u1.Function, (void*)HookGetActiveWindow);
                log_line("iat GetActiveWindow");
            }
        }
    }
}

static BOOL CALLBACK enum_window(HWND hwnd, LPARAM) {
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(hwnd)) return TRUE;
    RECT r;
    GetWindowRect(hwnd, &r);
    int area = (r.right - r.left) * (r.bottom - r.top);
    RECT cur;
    int curArea = 0;
    if (g_hwnd && GetWindowRect(g_hwnd, &cur)) curArea = (cur.right - cur.left) * (cur.bottom - cur.top);
    if (!g_hwnd || area > curArea) g_hwnd = hwnd;
    return TRUE;
}

static void open_log() {
    wchar_t path[MAX_PATH];
    if (!g_inst) return;
    DWORD n = GetModuleFileNameW(g_inst, path, MAX_PATH);
    if (!n || n >= MAX_PATH) return;
    wchar_t* slash = wcsrchr(path, L'\\');
    if (!slash) return;
    if ((size_t)(slash - path) + 14 >= MAX_PATH) return;
    wcscpy(slash + 1, L"lira-hook.log");
    g_log = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
}

static void place_window() {
    char* spec = getenv("LIRA_WINDOW");
    if (!spec || !g_hwnd) return;
    int x = 0, y = 0, w = 0, h = 0;
    if (sscanf(spec, "%d,%d,%d,%d", &x, &y, &w, &h) != 4) return;
    if (w < 320 || h < 240) return;
    SetWindowPos(g_hwnd, NULL, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
}

static void title_window() {
    wchar_t title[32];
    char* env = getenv("LIRA_TITLE");
    title[0] = 0;
    if (env && env[0]) {
        for (int i = 0; env[i] && i < 16; i++) {
            unsigned char c = (unsigned char)env[i];
            if (c < 32 || c > 126) {
                title[0] = 0;
                break;
            }
            title[i] = (wchar_t)c;
            title[i + 1] = 0;
        }
    }
    if (!title[0]) wcscpy(title, L"Lira");
    SetWindowTextW(g_hwnd, title);
    SetPropW(g_hwnd, L"LiraClient", (HANDLE)1);
}

static void refresh_window() {
    EnumWindows(enum_window, 0);
    if (!g_hwnd) return;
    title_window();
}

static DWORD WINAPI window_thread(void*) {
    bool moved = false;
    for (;;) {
        refresh_window();
        if (g_hwnd && !moved) {
            place_window();
            moved = true;
            log_line("window titled Lira");
        }
        static bool ultimaPatched = false;
        if (!ultimaPatched && GetModuleHandleA("ultima.dll")) {
            patch_iat(GetModuleHandleA("ultima.dll"));
            ultimaPatched = true;
        }
        Sleep(1000);
    }
}

static int parse_key(const char* s) {
    if (!_stricmp(s, "space")) return VK_SPACE;
    if (!_stricmp(s, "enter") || !_stricmp(s, "return")) return VK_RETURN;
    if (!_stricmp(s, "esc") || !_stricmp(s, "escape")) return VK_ESCAPE;
    if (!_stricmp(s, "tab")) return VK_TAB;
    if (!_stricmp(s, "shift")) return VK_SHIFT;
    if (!_stricmp(s, "ctrl")) return VK_CONTROL;
    if (!_stricmp(s, "alt")) return VK_MENU;
    if (!_stricmp(s, "up")) return VK_UP;
    if (!_stricmp(s, "down")) return VK_DOWN;
    if (!_stricmp(s, "left")) return VK_LEFT;
    if (!_stricmp(s, "right")) return VK_RIGHT;
    if (!_stricmp(s, "back")) return VK_BACK;
    if ((s[0] == 'f' || s[0] == 'F') && isdigit((unsigned char)s[1])) {
        int n = atoi(s + 1);
        if (n >= 1 && n <= 12) return VK_F1 + n - 1;
    }
    if (s[0] && !s[1]) {
        unsigned char c = (unsigned char)toupper((unsigned char)s[0]);
        if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) return c;
    }
    int n = atoi(s);
    if (n > 0 && n < 256) return n;
    return -1;
}

static void post_key(int vk, bool down) {
    if (!g_hwnd) return;
    LPARAM lp = 1 | (MapVirtualKeyA(vk, MAPVK_VK_TO_VSC) << 16);
    if (!down) lp |= (1 << 30) | (1 << 31);
    PostMessageA(g_hwnd, down ? WM_KEYDOWN : WM_KEYUP, vk, lp);
}

static void post_char(char c) {
    if (!g_hwnd) return;
    PostMessageA(g_hwnd, WM_CHAR, (WPARAM)(unsigned char)c, 1);
}

static void set_key(int vk, bool down) {
    if (vk < 0 || vk >= 256) return;
    InterlockedExchange(&g_force[vk], down ? 1 : 0);
    post_key(vk, down);
}

static void handle_line(char* line, char* reply, int replyMax) {
    while (*line == ' ') line++;
    char* end = line + strlen(line);
    while (end > line && (end[-1] == '\r' || end[-1] == '\n' || end[-1] == ' ')) *--end = 0;
    if (!_stricmp(line, "ping")) {
        strcpy(reply, "pong\n");
        return;
    }
    if (!_stricmp(line, "clear")) {
        for (int i = 0; i < 256; i++) g_force[i] = 0;
        for (int i = 0; i < 4; i++) g_mbtn[i] = 0;
        InterlockedExchange(&g_dx, 0);
        InterlockedExchange(&g_dy, 0);
        memset(g_sentDik, 0, sizeof(g_sentDik));
        strcpy(reply, "ok\n");
        return;
    }
    if (!_stricmp(line, "status")) {
        sprintf(reply, "fg=%d state=%ld data=%ld acquire=%ld hwnd=%d\n",
                background() ? 0 : 1, g_stateCalls, g_dataCalls, g_acquireCalls, g_hwnd ? 1 : 0);
        return;
    }
    char* sp = strchr(line, ' ');
    char cmd[32];
    if (!sp) {
        strncpy(cmd, line, 31);
        cmd[31] = 0;
    } else {
        int n = (int)(sp - line);
        if (n > 31) n = 31;
        memcpy(cmd, line, n);
        cmd[n] = 0;
        sp++;
    }
    if (!_stricmp(cmd, "down") || !_stricmp(cmd, "up")) {
        int vk = parse_key(sp ? sp : "");
        if (vk < 0) {
            strcpy(reply, "err key\n");
            return;
        }
        set_key(vk, !_stricmp(cmd, "down"));
        strcpy(reply, "ok\n");
        return;
    }
    if (!_stricmp(cmd, "tap")) {
        char* msText = sp ? strchr(sp, ' ') : NULL;
        if (msText) *msText++ = 0;
        int vk = parse_key(sp ? sp : "");
        int ms = msText ? atoi(msText) : 60;
        if (vk < 0) {
            strcpy(reply, "err key\n");
            return;
        }
        if (ms < 1) ms = 1;
        if (ms > 2000) ms = 2000;
        set_key(vk, true);
        Sleep(ms);
        set_key(vk, false);
        strcpy(reply, "ok\n");
        return;
    }
    if (!_stricmp(cmd, "text") && sp) {
        for (char* p = sp; *p; p++) {
            unsigned char c = (unsigned char)*p;
            SHORT vk = VkKeyScanA((char)c);
            int key = vk & 0xFF;
            if (key >= 0 && key < 256) {
                set_key(key, true);
                post_char((char)c);
                Sleep(30);
                set_key(key, false);
            } else {
                post_char((char)c);
                Sleep(30);
            }
        }
        strcpy(reply, "ok\n");
        return;
    }
    if (!_stricmp(cmd, "mouse") && sp) {
        int x = 0, y = 0;
        sscanf(sp, "%d %d", &x, &y);
        InterlockedExchangeAdd(&g_dx, x);
        InterlockedExchangeAdd(&g_dy, y);
        strcpy(reply, "ok\n");
        return;
    }
    if (!_stricmp(cmd, "button") && sp) {
        int index = 0, down = 0;
        sscanf(sp, "%d %d", &index, &down);
        if (index < 0 || index > 3) {
            strcpy(reply, "err button\n");
            return;
        }
        InterlockedExchange(&g_mbtn[index], down ? 1 : 0);
        strcpy(reply, "ok\n");
        return;
    }
    strcpy(reply, "err unknown\n");
}

static DWORD WINAPI pipe_thread(void*) {
    for (;;) {
        HANDLE pipe = CreateNamedPipeW(L"\\\\.\\pipe\\LiraInput", PIPE_ACCESS_DUPLEX,
                                       PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                                       1, 4096, 4096, 0, NULL);
        if (pipe == INVALID_HANDLE_VALUE) {
            log_line("pipe create failed");
            Sleep(1000);
            continue;
        }
        log_line("pipe ready");
        BOOL connected = ConnectNamedPipe(pipe, NULL) ? TRUE : (GetLastError() == ERROR_PIPE_CONNECTED);
        if (connected) {
            char buf[512];
            DWORD got = 0;
            if (ReadFile(pipe, buf, sizeof(buf) - 1, &got, NULL) && got > 0) {
                buf[got] = 0;
                char reply[256];
                reply[0] = 0;
                handle_line(buf, reply, sizeof(reply));
                DWORD wrote = 0;
                WriteFile(pipe, reply, (DWORD)strlen(reply), &wrote, NULL);
                FlushFileBuffers(pipe);
            }
        }
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
    }
}

static DWORD WINAPI init_thread(void*) {
    open_log();
    log_line("hook loaded");
    init_map();
    g_realAsync = (SHORT(WINAPI*)(int))GetProcAddress(GetModuleHandleA("user32.dll"), "GetAsyncKeyState");
    g_realKeyboard = (BOOL(WINAPI*)(PBYTE))GetProcAddress(GetModuleHandleA("user32.dll"), "GetKeyboardState");
    g_realForeground = (HWND(WINAPI*)())GetProcAddress(GetModuleHandleA("user32.dll"), "GetForegroundWindow");
    g_realActive = (HWND(WINAPI*)())GetProcAddress(GetModuleHandleA("user32.dll"), "GetActiveWindow");
    CreateThread(NULL, 0, window_thread, NULL, 0, NULL);
    patch_iat(GetModuleHandle(NULL));
    patch_iat(GetModuleHandleA("ultima.dll"));
    hook_directinput();
    pipe_thread(NULL);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, void*) {
    if (reason == DLL_PROCESS_ATTACH) {
        HANDLE existing = CreateMutexA(NULL, FALSE, "Local\\LiraInputHook");
        if (GetLastError() == ERROR_ALREADY_EXISTS) {
            if (existing) CloseHandle(existing);
            return TRUE;
        }
        g_inst = inst;
        DisableThreadLibraryCalls(inst);
        CreateThread(NULL, 0, init_thread, NULL, 0, NULL);
    }
    return TRUE;
}
