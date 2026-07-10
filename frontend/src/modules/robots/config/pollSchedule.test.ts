import { describe, expect, it } from 'vitest'

import { resolvePollMinutesFromRobot, snapPollMinutes, TRADING_POLL_MINUTE_OPTIONS } from './pollSchedule'

describe('pollSchedule', () => {
    it('snaps unknown minute value to nearest option', () => {
        expect(snapPollMinutes(3, TRADING_POLL_MINUTE_OPTIONS)).toBe(2)
        expect(snapPollMinutes(45, TRADING_POLL_MINUTE_OPTIONS)).toBe(30)
    })

    it('resolves schedule interval_seconds to minutes', () => {
        expect(
            resolvePollMinutesFromRobot({ interval_seconds: 300 }, {}, 2),
        ).toBe(5)
    })

    it('resolves poll_interval_hours from config when schedule missing', () => {
        expect(
            resolvePollMinutesFromRobot(null, { poll_interval_hours: 0.0833 }, 1),
        ).toBe(5)
    })

    it('defaults portfolio robot to 60 minutes', () => {
        expect(resolvePollMinutesFromRobot(null, {}, 1)).toBe(60)
    })
})
