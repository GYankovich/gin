import { describe, expect, it } from 'vitest'

import {
    clampPollMinutes,
    isPresetPollMinutes,
    resolvePollMinutesFromRobot,
    snapPollMinutes,
    TRADING_POLL_MINUTE_OPTIONS,
} from './pollSchedule'

describe('pollSchedule', () => {
    it('snaps unknown minute value to nearest option', () => {
        expect(snapPollMinutes(3, TRADING_POLL_MINUTE_OPTIONS)).toBe(2)
        expect(snapPollMinutes(45, TRADING_POLL_MINUTE_OPTIONS)).toBe(30)
    })

    it('detects preset vs custom minutes', () => {
        expect(isPresetPollMinutes(60, TRADING_POLL_MINUTE_OPTIONS)).toBe(true)
        expect(isPresetPollMinutes(360, TRADING_POLL_MINUTE_OPTIONS)).toBe(true)
        expect(isPresetPollMinutes(90, TRADING_POLL_MINUTE_OPTIONS)).toBe(false)
    })

    it('clamps free-form minutes', () => {
        expect(clampPollMinutes(0)).toBe(1)
        expect(clampPollMinutes(360)).toBe(360)
        expect(clampPollMinutes(9999)).toBe(1440)
    })

    it('resolves schedule interval_seconds to minutes', () => {
        expect(
            resolvePollMinutesFromRobot({ interval_seconds: 300 }, {}, 2),
        ).toBe(5)
    })

    it('preserves custom schedule minutes without snapping to presets', () => {
        expect(
            resolvePollMinutesFromRobot({ interval_seconds: 21600 }, {}, 1),
        ).toBe(360)
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
