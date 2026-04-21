import React, { useState, memo } from 'react'

interface RobotIllustrationProps {
    size?: number
    className?: string
    mode?: 'default' | 'active' | 'inactive'
    interactive?: boolean
}

export const RobotIllustration = memo(function RobotIllustration({
    size = 120,
    className = '',
    mode = 'default',
    interactive = true,
}: RobotIllustrationProps) {
    const [clicked, setClicked] = useState(false)
    const isActive = mode === 'active'
    const isInactive = mode === 'inactive'
    const accent = isInactive ? '#8b95a7' : 'var(--neon-cyan)'
    const accentSecondary = isInactive ? '#9aa3b2' : 'var(--neon-magenta)'
    const coreColor = isInactive ? '#808b9a' : 'var(--neon-violet)'

    const handleClick = () => {
        if (!interactive) return
        setClicked(true)
        setTimeout(() => setClicked(false), 600)
    }

    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 120 120"
            className={`robot-illustration ${clicked ? 'robot-illustration--clicked' : ''} ${className}`}
            onClick={handleClick}
            style={{ cursor: interactive ? 'pointer' : 'default' }}
        >
            {/* Antenna */}
            <line x1="60" y1="8" x2="60" y2="22" stroke={accent} strokeWidth="2">
                {!isInactive && (
                    <animateTransform
                        attributeName="transform"
                        type="rotate"
                        values="-5 60 22;5 60 22;-5 60 22"
                        dur={isActive ? '1.6s' : '3s'}
                        repeatCount="indefinite"
                    />
                )}
            </line>
            <circle cx="60" cy="6" r="4" fill={accentSecondary}>
                {!isInactive && (
                    <animate attributeName="opacity" values="1;0.4;1" dur={isActive ? '1.2s' : '2s'} repeatCount="indefinite" />
                )}
            </circle>

            {/* Head */}
            <rect x="30" y="22" width="60" height="44" rx="10" fill="var(--bg-card)" stroke={accent} strokeWidth="2" className="robot-head-clickable" />

            {/* Eyes */}
            <circle cx="45" cy="42" r={isInactive ? 4 : 6} fill={accent}>
                {!isInactive && <animate attributeName="r" values="6;6;1;6" dur={isActive ? '2.3s' : '4s'} repeatCount="indefinite" begin="0s" />}
            </circle>
            <circle cx="75" cy="42" r={isInactive ? 4 : 6} fill={accent}>
                {!isInactive && <animate attributeName="r" values="6;6;1;6" dur={isActive ? '2.3s' : '4s'} repeatCount="indefinite" begin="0s" />}
            </circle>

            {/* Mouth */}
            {isInactive ? (
                <path d="M45 58 Q60 50 75 58" fill="none" stroke={accentSecondary} strokeWidth="3" strokeLinecap="round" opacity="0.8" />
            ) : (
                <rect x="44" y="54" width="32" height="4" rx="2" fill={accentSecondary} opacity="0.8" />
            )}

            {/* Body */}
            <rect x="35" y="70" width="50" height="34" rx="6" fill="var(--bg-card)" stroke={accent} strokeWidth="1.5" />
            <circle cx="60" cy="87" r="5" fill={coreColor} opacity={isInactive ? 0.45 : 0.65}>
                {!isInactive && <animate attributeName="opacity" values="0.6;1;0.6" dur={isActive ? '0.8s' : '1.5s'} repeatCount="indefinite" />}
            </circle>

            {/* Arms */}
            <rect x="18" y="74" width="14" height="6" rx="3" fill={accent} opacity={isInactive ? 0.35 : 0.55} />
            <rect x="88" y="74" width="14" height="6" rx="3" fill={accent} opacity={isInactive ? 0.35 : 0.55} />

            {/* Legs */}
            <rect x="42" y="104" width="10" height="12" rx="4" fill={accent} opacity={isInactive ? 0.3 : 0.45} />
            <rect x="68" y="104" width="10" height="12" rx="4" fill={accent} opacity={isInactive ? 0.3 : 0.45} />
        </svg>
    )
})
