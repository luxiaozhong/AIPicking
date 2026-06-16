"""拼音工具函数"""
from pypinyin import pinyin, Style


def get_pinyin_initials(name: str) -> str:
    """提取中文名称的拼音首字母。非中文字符被忽略。

    例: 贵州茅台 → gzmt, 平安银行 → payx
    """
    if not name:
        return ""
    result = []
    for char in name:
        if '一' <= char <= '鿿':  # 仅中文字符
            result.append(pinyin(char, style=Style.FIRST_LETTER)[0][0])
    return ''.join(result)
