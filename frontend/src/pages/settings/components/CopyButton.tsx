import React from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCheck } from '@fortawesome/free-solid-svg-icons'
import { faClone } from '@fortawesome/free-regular-svg-icons'
import { copyText } from '@/pages/settings/utils'

type Props = {
    value: string
    label?: string
    onCopied?: () => void
    className?: string
}

export function CopyButton({ value, label = 'Копировать', onCopied, className = '' }: Props) {
    const [copied, setCopied] = React.useState(false)

    const handleCopy = async () => {
        const ok = await copyText(value)
        if (!ok) return
        setCopied(true)
        onCopied?.()
        window.setTimeout(() => setCopied(false), 1500)
    }

    return (
        <button
            type="button"
            className={`settings-copy-btn ${className}`.trim()}
            onClick={() => void handleCopy()}
            aria-label={label}
            title={label}
            disabled={!value}
        >
            <FontAwesomeIcon icon={copied ? faCheck : faClone} />
        </button>
    )
}
