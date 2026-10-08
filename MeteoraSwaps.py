import struct
from decimal import Decimal, localcontext


PROGRAM = 'cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG'
SOL = 'So11111111111111111111111111111111111111112'
USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
SWAPS = {bytes([248, 198, 158, 145, 225, 117, 135, 200]), bytes([65, 75, 63, 76, 235, 91, 91, 136])}
EVENT = bytes([228, 69, 165, 46, 81, 203, 154, 29, 189, 66, 51, 168, 38, 80, 117, 153])


def decode58(text):
    if not isinstance(text, str) or len(text) > 16000:
        raise ValueError('Invalid instruction data')
    value = 0
    for character in text:
        value = value * 58 + ALPHABET.index(character)
    return bytes(len(text) - len(text.lstrip('1'))) + value.to_bytes((value.bit_length() + 7) // 8, 'big')


def encode58(raw):
    value = int.from_bytes(raw, 'big')
    output = ''
    while value:
        value, digit = divmod(value, 58)
        output = ALPHABET[digit] + output
    return '1' * (len(raw) - len(raw.lstrip(bytes([0])))) + output


def event_values(raw):
    if len(raw) != 196 or raw[:16] != EVENT:
        raise ValueError('Unsupported swap event')
    cursor = 16
    def take(size):
        nonlocal cursor
        result = raw[cursor:cursor + size]
        cursor += size
        return result
    pool = encode58(take(32))
    direction, fee_mode, referral = take(3)
    if direction not in (0, 1) or referral not in (0, 1):
        raise ValueError('Invalid swap flags')
    take(17)
    result = struct.unpack('<QQQQ', take(32))
    sqrt_price = int.from_bytes(take(16), 'little')
    take(32)
    amount_in, gross_out, amount_out, timestamp, reserve_a, reserve_b = struct.unpack('<QQQQQQ', take(48))
    if not amount_in or not amount_out or not sqrt_price or amount_out > gross_out:
        raise ValueError('Invalid swap amounts')
    return pool, direction, amount_in, amount_out, timestamp, sqrt_price, reserve_a, reserve_b


def decode_swaps(transaction, signature, pools):
    if transaction.get('meta', {}).get('err') is not None:
        return []
    if signature not in transaction.get('transaction', {}).get('signatures', []):
        raise ValueError('Transaction signature mismatch')
    decimals = {SOL: 9, USDC: 6}
    for field in ['preTokenBalances', 'postTokenBalances']:
        for balance in transaction.get('meta', {}).get(field, []):
            mint, places = balance.get('mint'), balance.get('uiTokenAmount', {}).get('decimals')
            if not isinstance(mint, str) or type(places) is not int or not 0 <= places <= 18:
                continue
            if mint in decimals and decimals[mint] != places:
                raise ValueError('Inconsistent mint decimals')
            decimals[mint] = places
    message = transaction.get('transaction', {}).get('message', {})
    groups = {group['index']: group.get('instructions', []) for group in transaction.get('meta', {}).get('innerInstructions', [])}
    trades = []
    ordinal = 0
    for index, outer in enumerate(message.get('instructions', [])):
        current = None
        waiting = False
        for instruction in [outer, *groups.get(index, [])]:
            if instruction.get('programId') != PROGRAM or not isinstance(instruction.get('data'), str):
                continue
            raw = decode58(instruction['data'])
            if raw[:8] in SWAPS:
                if waiting:
                    raise ValueError('Missing supported swap event')
                accounts = instruction.get('accounts', [])
                current = accounts if len(accounts) >= 9 else None
                waiting = current is not None and current[1] in pools
                continue
            if raw[:16] != EVENT:
                continue
            event_index = ordinal
            ordinal += 1
            if current is None:
                raise ValueError('Swap event has no instruction')
            pool, direction, amount_in, amount_out, timestamp, sqrt_price, reserve_a, reserve_b = event_values(raw)
            if type(transaction.get('blockTime')) is not int or abs(timestamp - transaction['blockTime']) > 120:
                raise ValueError('Swap timestamp mismatch')
            if current[1] != pool:
                raise ValueError('Swap pool mismatch')
            waiting = False
            if pool not in pools:
                continue
            mint_a, mint_b = current[6:8]
            base = pools[pool]
            if base not in (mint_a, mint_b):
                raise ValueError('Tracked token is outside pool')
            quote = mint_b if base == mint_a else mint_a
            if quote not in (SOL, USDC) or base not in decimals:
                raise ValueError('Unsupported quote or missing mint decimals')
            buying = (direction == 1) if base == mint_a else (direction == 0)
            with localcontext() as context:
                context.prec = 80
                base_amount = Decimal(amount_out if buying else amount_in).scaleb(-decimals[base])
                quote_amount = Decimal(amount_in if buying else amount_out).scaleb(-decimals[quote])
                ratio = (Decimal(sqrt_price) / Decimal(2 ** 64)) ** 2 * (Decimal(10) ** (decimals[mint_a] - decimals[mint_b]))
                spot = ratio if base == mint_a else 1 / ratio
                base_reserve = Decimal(reserve_a if base == mint_a else reserve_b).scaleb(-decimals[base])
                quote_reserve = Decimal(reserve_b if base == mint_a else reserve_a).scaleb(-decimals[quote])
                trades.append({'signature': signature, 'event_index': event_index, 'pool': pool, 'address': base, 'wallet': current[8], 'side': 'Buy' if buying else 'Sell', 'base_amount': str(base_amount), 'quote_amount': str(quote_amount), 'quote_mint': quote, 'price_quote': str(spot), 'execution_price_quote': str(quote_amount / base_amount), 'liquidity_quote': str(base_reserve * spot + quote_reserve), 'slot': transaction['slot'], 'block_time': transaction.get('blockTime'), 'event_time': timestamp, 'confirmation': 'confirmed'})
        if waiting:
            raise ValueError('Missing supported swap event')
    return trades
