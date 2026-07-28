import type { ValidationIssue } from '@/pages/testing/refactored/types/forms'

/** Map validation issues → `form.invalid` field flags for UI highlights. */
export function issuesToInvalidFields(issues: ValidationIssue[]): Record<string, boolean> {
    const out: Record<string, boolean> = {}
    for (const issue of issues) {
        if (issue.field === 'period') {
            out.period = true
        } else {
            out[issue.field] = true
        }
    }
    return out
}

export function formatValidationIssuesForToast(issues: ValidationIssue[]): string {
    if (issues.length === 1) return issues[0].message
    return issues.map((i, idx) => `${idx + 1}. ${i.message}`).join(' · ')
}
