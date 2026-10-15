// Starts one Blue Burst client, marks that window, and injects the input hook.
// Account and paths come from launch.cfg, which is deleted as soon as it is read.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

static wchar_t g_dir[MAX_PATH];

static void dir_of_exe() {
    GetModuleFileNameW(NULL, g_dir, MAX_PATH);
    wchar_t* slash = wcsrchr(g_dir, L'\\');
    if (slash) *slash = 0;
}

static void join_path(wchar_t* out, int cap, const wchar_t* name) {
    swprintf(out, cap, L"%s\\%s", g_dir, name);
}

static void log_line(const char* text) {
    wchar_t path[MAX_PATH];
    join_path(path, MAX_PATH, L"lira-launch.log");
    FILE* f = NULL;
    if (_wfopen_s(&f, path, L"a") != 0 || !f) return;
    fprintf(f, "%s\n", text);
    fclose(f);
}

static void reg_cmd(const wchar_t* args) {
    wchar_t cmd[600];
    swprintf(cmd, 600, L"reg.exe %s", args);
    STARTUPINFOW si;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi;
    memset(&pi, 0, sizeof(pi));
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) return;
    WaitForSingleObject(pi.hProcess, 15000);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
}

struct RegistryHold {
    bool armed;
    RegistryHold() : armed(false) {}
    bool source_exists() {
        HKEY key = NULL;
        LONG result = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\SonicTeam\\PSOBB", 0, KEY_READ, &key);
        if (result != ERROR_SUCCESS) return false;
        RegCloseKey(key);
        return true;
    }
    bool backup() {
        reg_cmd(L"copy HKCU\\Software\\SonicTeam\\PSOBB HKCU\\Software\\SonicTeam\\PSOBB_LiraHold /s /f");
        HKEY key = NULL;
        if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\SonicTeam\\PSOBB_LiraHold", 0, KEY_READ, &key) != ERROR_SUCCESS) {
            return false;
        }
        RegCloseKey(key);
        armed = true;
        return true;
    }
    void apply(const wchar_t* account) {
        HKEY key = NULL;
        if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\SonicTeam\\PSOBB", 0, KEY_SET_VALUE, &key) != ERROR_SUCCESS) return;
        RegSetValueExW(key, L"ACCOUNT", 0, REG_SZ, (const BYTE*)account, (DWORD)((wcslen(account) + 1) * sizeof(wchar_t)));
        DWORD check = 0;
        RegSetValueExW(key, L"ACCOUNT_CHECK", 0, REG_DWORD, (const BYTE*)&check, sizeof(check));
        RegDeleteValueW(key, L"Password");
        RegCloseKey(key);
        log_line("login pointed at the configured account");
    }
    void restore() {
        if (!armed) return;
        reg_cmd(L"copy HKCU\\Software\\SonicTeam\\PSOBB_LiraHold HKCU\\Software\\SonicTeam\\PSOBB /s /f");
        reg_cmd(L"delete HKCU\\Software\\SonicTeam\\PSOBB_LiraHold /f");
        armed = false;
        log_line("registry restored");
    }
    ~RegistryHold() { restore(); }
};

struct Secret {
    wchar_t password[32];
    Secret() { password[0] = 0; }
    ~Secret() { SecureZeroMemory(password, sizeof(password)); }
};

static bool plain_ascii(const char* text, int maxLen) {
    int count = 0;
    for (const unsigned char* cursor = (const unsigned char*)text; *cursor; cursor++, count++) {
        if (*cursor < 32 || *cursor > 126) return false;
        if (count >= maxLen) return false;
    }
    return true;
}

static bool utf8_to_wide(const char* utf8, wchar_t* out, int cap) {
    return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, out, cap) > 0;
}

static bool load_cfg(wchar_t* gameDir, int gameCap, wchar_t* account, int accountCap, Secret* secret, char* windowSpec, int windowCap, wchar_t* title, int titleCap) {
    wchar_t path[MAX_PATH];
    join_path(path, MAX_PATH, L"launch.cfg");
    FILE* file = NULL;
    if (_wfopen_s(&file, path, L"rb") != 0 || !file) return false;
    char raw[8192];
    size_t got = fread(raw, 1, sizeof(raw) - 1, file);
    fclose(file);
    DeleteFileW(path);
    if (!got || got >= sizeof(raw) - 1) {
        SecureZeroMemory(raw, sizeof(raw));
        return false;
    }
    raw[got] = 0;
    gameDir[0] = 0;
    account[0] = 0;
    secret->password[0] = 0;
    strncpy(windowSpec, "100,100,1280,720", windowCap - 1);
    windowSpec[windowCap - 1] = 0;
    wcscpy(title, L"Lira");

    char* cursor = raw;
    while (cursor && *cursor) {
        char* line = cursor;
        char* next = strchr(cursor, '\n');
        if (next) {
            *next = 0;
            cursor = next + 1;
        } else {
            cursor = NULL;
        }
        if (line[0] && line[strlen(line) - 1] == '\r') line[strlen(line) - 1] = 0;
        char* eq = strchr(line, '=');
        if (!eq || eq == line) continue;
        *eq = 0;
        char* value = eq + 1;
        if (strcmp(line, "game_dir") == 0) {
            if (!utf8_to_wide(value, gameDir, gameCap)) gameDir[0] = 0;
        } else if (strcmp(line, "account") == 0) {
            if (plain_ascii(value, 16)) utf8_to_wide(value, account, accountCap);
        } else if (strcmp(line, "password") == 0) {
            if (!value[0]) {
                secret->password[0] = 0;
            } else if (!plain_ascii(value, 16) || !utf8_to_wide(value, secret->password, 32)) {
                SecureZeroMemory(raw, sizeof(raw));
                return false;
            }
        } else if (strcmp(line, "window") == 0) {
            int x = 0, y = 0, w = 0, h = 0;
            if (sscanf(value, "%d,%d,%d,%d", &x, &y, &w, &h) == 4 && w >= 320 && h >= 240) {
                sprintf(windowSpec, "%d,%d,%d,%d", x, y, w, h);
            }
        } else if (strcmp(line, "character") == 0) {
            if (plain_ascii(value, 16) && value[0]) utf8_to_wide(value, title, titleCap);
        }
    }
    SecureZeroMemory(raw, sizeof(raw));
    return gameDir[0] && account[0];
}

static void write_pid(DWORD pid) {
    wchar_t path[MAX_PATH];
    join_path(path, MAX_PATH, L"lira.pid");
    FILE* file = NULL;
    if (_wfopen_s(&file, path, L"w") != 0 || !file) return;
    fprintf(file, "%lu\n", pid);
    fclose(file);
}

static bool pid_alive(DWORD pid) {
    if (!pid) return false;
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) return false;
    DWORD code = 0;
    BOOL ok = GetExitCodeProcess(process, &code);
    CloseHandle(process);
    return ok && code == STILL_ACTIVE;
}

static bool already_running() {
    wchar_t path[MAX_PATH];
    join_path(path, MAX_PATH, L"lira.pid");
    FILE* file = NULL;
    if (_wfopen_s(&file, path, L"r") != 0 || !file) return false;
    unsigned long pid = 0;
    fscanf_s(file, "%lu", &pid);
    fclose(file);
    return pid_alive((DWORD)pid);
}

static bool inject(HANDLE process, const wchar_t* dll) {
    size_t bytes = (wcslen(dll) + 1) * sizeof(wchar_t);
    void* remote = VirtualAllocEx(process, NULL, bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote) return false;
    if (!WriteProcessMemory(process, remote, dll, bytes, NULL)) {
        VirtualFreeEx(process, remote, 0, MEM_RELEASE);
        return false;
    }
    FARPROC load = GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW");
    HANDLE thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)load, remote, 0, NULL);
    if (!thread) {
        VirtualFreeEx(process, remote, 0, MEM_RELEASE);
        return false;
    }
    WaitForSingleObject(thread, 15000);
    DWORD code = 0;
    GetExitCodeThread(thread, &code);
    CloseHandle(thread);
    VirtualFreeEx(process, remote, 0, MEM_RELEASE);
    return code != 0;
}

struct Found {
    HWND hwnd;
    DWORD pid;
};

static BOOL CALLBACK find_pid_window(HWND hwnd, LPARAM lp) {
    Found* found = (Found*)lp;
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (pid != found->pid || !IsWindowVisible(hwnd)) return TRUE;
    RECT rect;
    if (!GetWindowRect(hwnd, &rect)) return TRUE;
    int area = (rect.right - rect.left) * (rect.bottom - rect.top);
    if (area < 200 * 200) return TRUE;
    found->hwnd = hwnd;
    return TRUE;
}

static bool pipe_cmd(const char* cmd, char* reply, int replyMax) {
    HANDLE handle = CreateFileW(L"\\\\.\\pipe\\LiraInput", GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (handle == INVALID_HANDLE_VALUE) return false;
    DWORD wrote = 0;
    BOOL ok = WriteFile(handle, cmd, (DWORD)strlen(cmd), &wrote, NULL);
    if (!ok) {
        CloseHandle(handle);
        return false;
    }
    DWORD got = 0;
    ok = ReadFile(handle, reply, replyMax - 1, &got, NULL);
    CloseHandle(handle);
    if (!ok) return false;
    reply[got] = 0;
    return true;
}

static bool pipe_line(const char* cmd) {
    char reply[128];
    return pipe_cmd(cmd, reply, sizeof(reply));
}

static bool pipe_text(const wchar_t* text) {
    char ascii[64];
    char cmd[80];
    if (!text || !text[0]) return true;
    if (WideCharToMultiByte(CP_UTF8, 0, text, -1, ascii, sizeof(ascii), NULL, NULL) <= 0) return false;
    if (strlen(ascii) > 48) return false;
    strcpy(cmd, "text ");
    strcat(cmd, ascii);
    strcat(cmd, "\n");
    return pipe_line(cmd);
}

static void place(HWND hwnd, const char* windowSpec) {
    int x = 100, y = 100, w = 1280, h = 720;
    sscanf(windowSpec, "%d,%d,%d,%d", &x, &y, &w, &h);
    if (w < 320 || h < 240) return;
    SetWindowPos(hwnd, NULL, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
}

int wmain() {
    dir_of_exe();
    if (already_running()) {
        printf("Her client is already running.\n");
        return 0;
    }

    wchar_t gameDir[MAX_PATH];
    wchar_t account[32];
    wchar_t title[32];
    char windowSpec[64];
    Secret secret;
    if (!load_cfg(gameDir, MAX_PATH, account, 32, &secret, windowSpec, sizeof(windowSpec), title, 32)) {
        printf("launch.cfg is missing or incomplete. Start her with python run.py --launch\n");
        return 1;
    }

    wchar_t exe[MAX_PATH];
    swprintf(exe, MAX_PATH, L"%s\\psobb.exe", gameDir);
    if (GetFileAttributesW(exe) == INVALID_FILE_ATTRIBUTES) {
        printf("psobb.exe was not found in the game folder\n");
        return 1;
    }

    RegistryHold hold;
    if (hold.source_exists()) {
        if (!hold.backup()) {
            printf("Could not save the current login. She was not started.\n");
            return 1;
        }
        hold.apply(account);
    }

    wchar_t dll[MAX_PATH];
    join_path(dll, MAX_PATH, L"lira_hook.dll");
    SetEnvironmentVariableA("LIRA_WINDOW", windowSpec);
    char titleAscii[32];
    titleAscii[0] = 0;
    WideCharToMultiByte(CP_UTF8, 0, title, -1, titleAscii, sizeof(titleAscii), NULL, NULL);
    SetEnvironmentVariableA("LIRA_TITLE", titleAscii);

    wchar_t cmd[MAX_PATH + 8];
    swprintf(cmd, MAX_PATH + 8, L"\"%s\"", exe);
    STARTUPINFOW si;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi;
    memset(&pi, 0, sizeof(pi));
    if (!CreateProcessW(exe, cmd, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, gameDir, &si, &pi)) {
        printf("could not start psobb (%lu)\n", GetLastError());
        return 1;
    }
    write_pid(pi.dwProcessId);
    printf("started her client, pid %lu\n", pi.dwProcessId);
    bool hooked = inject(pi.hProcess, dll);
    ResumeThread(pi.hThread);
    if (!hooked) hooked = inject(pi.hProcess, dll);
    if (!hooked) {
        printf("inject failed (%lu)\n", GetLastError());
        log_line("inject failed");
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 1;
    }
    printf("hook loaded\n");

    Found found = {NULL, pi.dwProcessId};
    for (int i = 0; i < 80 && !found.hwnd; i++) {
        EnumWindows(find_pid_window, (LPARAM)&found);
        Sleep(250);
    }
    if (found.hwnd) {
        SetPropW(found.hwnd, L"LiraClient", (HANDLE)1);
        SetWindowTextW(found.hwnd, title);
        place(found.hwnd, windowSpec);
        printf("window marked\n");
    } else {
        printf("window not up yet\n");
    }

    char reply[128];
    bool ready = false;
    for (int i = 0; i < 40; i++) {
        if (pipe_cmd("ping\n", reply, sizeof(reply)) && strstr(reply, "pong")) {
            ready = true;
            break;
        }
        Sleep(250);
    }
    if (!ready) {
        printf("hook pipe did not answer\n");
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 1;
    }

    pipe_line("tap space 80\n");
    Sleep(1500);
    pipe_line("tap space 80\n");
    Sleep(2000);
    pipe_text(account);
    pipe_line("tap tab 40\n");
    if (secret.password[0]) {
        pipe_text(secret.password);
        pipe_line("tap enter 40\n");
        printf("login keys sent\n");
        log_line("login keys sent");
        Sleep(8000);
    } else {
        printf("Password is empty. Finish login in her window.\n");
        Sleep(2000);
    }
    hold.restore();
    printf("Her client is pid %lu. The saved login was put back.\n", pi.dwProcessId);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
