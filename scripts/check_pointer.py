"""Manual native Windows pointer probe; no text logging or model requests."""
import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser(description='指向普通单词验证取词；不输出原文、不调用模型')
    parser.add_argument('--delay', type=int, default=5, choices=range(2, 31), metavar='2..30')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--no-ocr', action='store_true', help='仅测试 UI Automation 指针接口')
    group.add_argument('--ocr-only', action='store_true', help='仅测试本机截图 OCR，请指向非敏感普通文字')
    args = parser.parse_args()
    if sys.platform != 'win32':
        print('ENVIRONMENT_RESTRICTED: pointer probe requires native Windows')
        return 2
    from wordloom.network import Cancellation
    from wordloom.platforms.pointer import WindowsPointer
    from wordloom.pointer import parse_pointer
    from wordloom.providers import ApiError
    backend = WindowsPointer()
    backend.warmup()
    print(f'{args.delay} 秒内切换到目标程序，将鼠标指向一个普通单词，无需选择；保持窗口不变。', flush=True)
    try:
        time.sleep(args.delay)
        target = backend.capture_target()
        start = time.monotonic()
        token = Cancellation()
        if args.ocr_only:
            data = dict(x=target.x, y=target.y, window=target.window, foreground=target.foreground)
            found = parse_pointer(backend.ocr.request(data, token, 8, lambda: backend.is_current(target)), target)
        else:
            found = backend.read(target, token, not args.no_ocr)
        print(f'PASS: source={found.source}, word_chars={len(found.word)}, context_chars={len(found.context)}, elapsed={time.monotonic()-start:.2f}s')
        print('仅验证此次原生读取；未输出原文、未发送模型请求，不代表其他应用或浮窗通过。')
        return 0
    except ApiError as exc:
        print('FAIL:', exc.code, str(exc))
        return 1
    finally:
        backend.close()


if __name__ == '__main__':
    raise SystemExit(main())
