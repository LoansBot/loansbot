"""Describes something which can take an anchor text followed by a series of
tokens and parse them out. Tokens may be optional and there may be fallbacks
within a single token.

This parser is always greedy; it will attempt to parse optional tokens before
moving on, and it will attempt to parse all fallbacks in order.
"""
import pytypeutils as tus
from parsing.token import Token


class Parser:
    """A parser, which takes a collection of tokens and attempts to parse them
    in order.

    Attributes:
        anchor (str): A plain-text anchor for the start of the token. For
            example, the value '$check ' means we will only look for tokens
            after the string literal '$check '.
        tokens (list): A list of tokens, where each token is actually a dict
            containing the following keys:

            token (parsing.token.Token): The underlying parsable token. This
                may encapsulate multiple fallback tokens.
            optional (bool): Determines what should happen if this token isn't
                matched at the expected point. If optional is true, the token
                result will be set to None and parsing will continue.
                Otherwise, if optinoal is false, parsing will stop.
    """
    def __init__(self, anchor, tokens):
        tus.check(anchor=(anchor, str), tokens=(tokens, (list, tuple)))
        for idx, token in enumerate(tokens):
            tus.check(**{f'tokens_{idx}': (token, dict)})
            tus.check(**{
                f'tokens_{idx}_token': (token['token'], Token),
                f'tokens_{idx}_optional': (token['optional'], bool)
            })
        self.anchor = anchor
        self.tokens = tokens

    def parse(self, text):
        """Attempts to parse the given text according to the rules of this
        parser. If the anchor text is found and then all non-optional tokens
        are found in the appropriate order, this will return the result of
        each token (where omitted optional tokens are given the value None).
        Otherwise this returns None

        Returns:
            (list, None): The value of each token in order, with omitted
                optional tokens assigned None, if a match was found. Otherwise,
                this returns None
        """
        start_index = -1
        while True:
            start_index = text.find(self.anchor, start_index + 1)
            if start_index < 0:
                break

            token_index = start_index + len(self.anchor)
            result = []
            for token in self.tokens:
                if token_index < len(self.anchor):
                    num_consumed, value = token['token'].consume(text, token_index)
                else:
                    num_consumed, value = (None, None)

                if num_consumed is None:
                    if not token['optional']:
                        break
                    result.append(None)
                else:
                    result.append(value)
                    token_index += num_consumed

            if len(result) == len(self.tokens):
                return result

        return None
