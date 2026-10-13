"""Manual Windows UIA probe. Never prints selected text or calls a model."""
import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser(description='选择文字后验证 UI Automation；不会输出选区内容或调用模型')
    parser.add_argument('--delay', type=int, default=5, choices=range(2, 31), metavar='2..30')
    args = parser.parse_args()
    if sys.platform != 'win32':
        print('ENVIRONMENT_RESTRICTED: selection probe requires native Windows')
        return 2
    from wordloom.network import Cancellation
    from wordloom.platforms.selection import WindowsSelection
    from wordloom.providers import ApiError
    backend = WindowsSelection()
    print(f'{args.delay} 秒内切换到记事本或浏览器，选中一段普通文本并保持前台。', flush=True)
    time.sleep(args.delay)
    try:
        target = backend.capture_target()
        text = backend.read(target, Cancellation())
    except ApiError as exc:
        print('FAIL:', exc.code, str(exc))
        return 1
    finally:
        backend.cancel()
    print(f'PASS: UI Automation 读取 {len(text)} 个字符；未输出原文，未发送模型请求。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
