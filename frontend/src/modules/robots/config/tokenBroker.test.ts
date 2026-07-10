import { describe, expect, it } from 'vitest'

import { brokerFromTokenId, brokerFromTokenType } from './tokenBroker'

describe('tokenBroker', () => {
    it('maps token type 1 to tinvest', () => {
        expect(brokerFromTokenType({ type: 1, typeName: 'T-Invest' })).toBe('tinvest')
    })

    it('maps token type 2 to bybit', () => {
        expect(brokerFromTokenType({ type: 2, typeName: 'ByBit' })).toBe('bybit')
    })

    it('resolves broker from token catalog', () => {
        expect(
            brokerFromTokenId(25, [{ id: 25, token_type: { type: 2, typeName: 'ByBit', typeDesc: '' } }]),
        ).toBe('bybit')
    })
})
