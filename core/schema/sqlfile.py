"""Split a MariaDB/MySQL script into statements.

Quoted strings, backtick names, and comments may contain semicolons. Plain
comments are dropped. Versioned comments (`/*!40101 ... */`) are kept because
the server runs them.
"""

from pathlib import Path


def _skip_to_line_end(text, index):
    end = text.find('\n', index)
    return len(text) if end == -1 else end


def split_statements(text):
    text = text.replace('\r\n', '\n')
    statements = []
    buffer = []
    quote = None
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if quote:
            buffer.append(char)
            if char == '\\' and quote != '`' and index + 1 < length:
                buffer.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                if index + 1 < length and text[index + 1] == quote:
                    buffer.append(quote)
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in ("'", '"', '`'):
            quote = char
            buffer.append(char)
            index += 1
            continue

        if text.startswith('--', index) and (index + 2 == length or text[index + 2] in ' \t\n'):
            index = _skip_to_line_end(text, index)
            continue

        if char == '#':
            index = _skip_to_line_end(text, index)
            continue

        if text.startswith('/*', index) and not text.startswith('/*!', index):
            end = text.find('*/', index + 2)
            index = length if end == -1 else end + 2
            continue

        if char == ';':
            statement = ''.join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    if quote:
        raise ValueError(f'Unterminated {quote} quote in SQL script.')

    tail = ''.join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def read_statements(path):
    return split_statements(Path(path).read_text(encoding='utf-8'))
