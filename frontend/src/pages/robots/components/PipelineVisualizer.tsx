import React from 'react'

export type RobotEditorStage = 'general' | 'p1' | 'p2' | 'p3' | 'risk'

export type PipelineVisualizerNode = {
    id: RobotEditorStage
    icon: string
    title: string
    hidden?: boolean
}

type Props = {
    nodes: PipelineVisualizerNode[]
    activeStage: RobotEditorStage
    onStageChange: (stage: RobotEditorStage) => void
}

export function PipelineVisualizer({ nodes, activeStage, onStageChange }: Props) {
    const visible = nodes.filter(n => !n.hidden)
    if (!visible.length) return null

    return (
        <nav className="pipeline-visualizer" aria-label="Этапы настройки робота">
            <div className="pipeline-visualizer__track">
                {visible.map((node, idx) => (
                    <React.Fragment key={node.id}>
                        {idx > 0 && <span className="pipeline-visualizer__connector" aria-hidden />}
                        <button
                            type="button"
                            className={`pipeline-visualizer__node${
                                activeStage === node.id ? ' pipeline-visualizer__node--active' : ''
                            }`}
                            onClick={() => onStageChange(node.id)}
                            aria-current={activeStage === node.id ? 'step' : undefined}
                            aria-label={node.title}
                            title={node.title}
                        >
                            <span className="pipeline-visualizer__icon" aria-hidden>
                                {node.icon}
                            </span>
                            <span className="pipeline-visualizer__title">{node.title}</span>
                        </button>
                    </React.Fragment>
                ))}
            </div>
        </nav>
    )
}
