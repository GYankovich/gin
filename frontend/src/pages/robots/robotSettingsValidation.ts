export type {
    ConfigValidationIssue as ValidationIssue,
    MoexRobotSettingsCheckInput as RobotSettingsValidationInput,
} from '@/modules/robots/config/validate/collectIssues'
export {
    candleIntervalMinutes,
    collectIssues as collectRobotSettingsIssues,
    collectMoexSettingsIssues as validateRobotSettings,
    hasBlockingValidationIssues,
} from '@/modules/robots/config/validate/collectIssues'
