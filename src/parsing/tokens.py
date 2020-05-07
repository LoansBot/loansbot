"""Describes the general token framework, which is the token interface
and delegating implementations like the FallbackToken
"""
import pytypeutils as tus
import re


class Token:
    """The base interface for all parsing tokens. A token encapsulates the
    ability to take a string and an offset and return how many characters
    were consumed and the parsed value of the token.
    """
    def consume(self, text, offset):
        """Attempt to consume this token starting at the given offset within
        the specified text. If the consumption is successful the first result
        is the number of characters consumed, otherwise the first result is
        None.

        Args:
            text (str): The complete text that is being parsed
            offset (int): Where this token should start its search from
        Returns:
            ((int, None), Any): If the consumption was successful, the first
                result is the number of characters consumed and the second
                result is the value of the token. Otherwise, this returns
                None, None.
        """
        raise NotImplementedError


class FallbackToken(Token):
    """Describes a token which attempts the list of tokens in order, succeeding
    as soon as the first one succeeds. Hence this only fails if none of the
    children succeed.

    Attributes:
        children (list): A list of children token in the order they should be
            attempted.
    """
    def __init__(self, children):
        tus.check(children=(children, (tuple, list)))
        tus.check_listlike(children=(children, Token))
        self.children = children

    def consume(self, text, offset):
        tus.check(text=(text, str), offset=(offset, int))

        for child in self.children:
            num_consumed, val = child.consume(text, offset)
            if num_consumed is not None:
                return (num_consumed, val)
        return None, None


class RegexToken(Token):
    """Describes a token which just matches a regex and then takes the value
    of a particular capture group. The regular expression will be sent the
    substring starting after the offset. The regular expression MUST start
    with \\A.

    Attributes:
        regex (str): The regular expression to apply, starting with \\A
        capture (int, None): The capture group to take as the value if the
            regex matches, or nil just to use the match object.
    """
    def __init__(self, regex, capture):
        tus.check(regex=(regex, str), capture=(capture, (int, type(None))))
        self.regex = regex
        self.capture = capture

    def consume(self, text, offset):
        match = re.search(self.regex, text[offset:])
        if match is None:
            return None, None
        return len(match.group()), (match if self.capture is None else match.group(self.capture))


class TransformedToken(Token):
    """Describes a token which takes the value of the inner token if it exists
    and manipulates it. If the inner token failed to match, this also fails to
    match. If the transform returns None, this treats it as a failure to match.

    Attributes:
        child (Token): The main token
        transform (callable): The transform applied to the output of the inner
            token if it exists
    """
    def __init__(self, child, transform):
        tus.check(child=(child, Token))
        tus.check_callable(transform=transform)
        self.child = child
        self.transform = transform

    def consume(self, text, offset):
        consumed, val = self.child.consume(text, offset)
        if consumed is None:
            return None, None
        new_val = self.transform(val)
        if new_val is None:
            return None, None
        return consumed, new_val
