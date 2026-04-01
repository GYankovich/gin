import React, { useState, memo } from 'react'

interface RobotIllustrationProps {
    size?: number
    className?: string
}

export const RobotIllustration = memo(function RobotIllustration({ size = 120, className = '' }: RobotIllustrationProps) {
    const [clicked, setClicked] = useState(false)

    const handleClick = () => {
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
            style={{ cursor: 'pointer' }}
        >
            {/* Antenna */}
            <line x1="60" y1="8" x2="60" y2="22" stroke="var(--neon-cyan)" strokeWidth="2">
                <animateTransform attributeName="transform" type="rotate" values="-5 60 22;5 60 22;-5 60 22" dur="3s" repeatCount="indefinite" />
            </line>
            <circle cx="60" cy="6" r="4" fill="var(--neon-magenta)">
                <animate attributeName="opacity" values="1;0.4;1" dur="2s" repeatCount="indefinite" />
            </circle>

            {/* Head */}
            <rect x="30" y="22" width="60" height="44" rx="10" fill="var(--bg-card)" stroke="var(--neon-cyan)" strokeWidth="2" className="robot-head-clickable" />

            {/* Eyes */}
            <circle cx="45" cy="42" r="6" fill="var(--neon-cyan)">
                <animate attributeName="r" values="6;6;1;6" dur="4s" repeatCount="indefinite" begin="0s" />
            </circle>
            <circle cx="75" cy="42" r="6" fill="var(--neon-cyan)">
                <animate attributeName="r" values="6;6;1;6" dur="4s" repeatCount="indefinite" begin="0s" />
            </circle>

            {/* Mouth */}
            <rect x="44" y="54" width="32" height="4" rx="2" fill="var(--neon-magenta)" opacity="0.7" />

            {/* Body */}
            <rect x="35" y="70" width="50" height="34" rx="6" fill="var(--bg-card)" stroke="var(--neon-cyan)" strokeWidth="1.5" />
            <circle cx="60" cy="87" r="5" fill="var(--neon-violet)" opacity="0.6">
                <animate attributeName="opacity" values="0.6;1;0.6" dur="1.5s" repeatCount="indefinite" />
            </circle>

            {/* Arms */}
            <rect x="18" y="74" width="14" height="6" rx="3" fill="var(--neon-cyan)" opacity="0.5" />
            <rect x="88" y="74" width="14" height="6" rx="3" fill="var(--neon-cyan)" opacity="0.5" />

            {/* Legs */}
            <rect x="42" y="104" width="10" height="12" rx="4" fill="var(--neon-cyan)" opacity="0.4" />
            <rect x="68" y="104" width="10" height="12" rx="4" fill="var(--neon-cyan)" opacity="0.4" />
        </svg>
    )
})
