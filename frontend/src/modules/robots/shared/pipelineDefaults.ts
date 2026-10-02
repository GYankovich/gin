import type { PipelineFilter } from '@/modules/robots/shared/pipeline'
import { moexTestingPipelineFromPreset } from '@/modules/robots/config/universeFilterPresets'

/** Стартовый конвейер для grain_seed — пресет «Умеренная». */
export function createDefaultTestingPipelineFilters(): PipelineFilter[] {
    return moexTestingPipelineFromPreset('moderate').filters
}
