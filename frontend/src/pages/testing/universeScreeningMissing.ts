import { FILTER_META, type PipelineFilter } from '@/pages/testing/testingPipeline'

import { MOEX_TESTING_PIPELINE_FILTER_PRESETS } from '@/modules/robots/config/universeFilterPresets'

import {

    CRYPTO_FILTER_META,

    cryptoScreeningFiltersFromPreset,

    type CryptoScreeningFilter,

} from '@/pages/testing/cryptoScreeningPipeline'



/** Типы фильтров crypto pipeline, отсутствующие относительно пресета moderate. */

export function getCryptoPipelineMissingFilterLabels(filters: CryptoScreeningFilter[]): string[] {

    const expected = cryptoScreeningFiltersFromPreset('moderate').map(f => f.type)

    const present = new Set(filters.map(f => f.type))

    return expected.filter(t => !present.has(t)).map(t => CRYPTO_FILTER_META[t]?.label ?? t)

}



/** Типы фильтров pipeline, отсутствующие относительно эталонного пресета moderate. */

export function getMoexPipelineMissingFilterLabels(filters: PipelineFilter[]): string[] {

    const expected = MOEX_TESTING_PIPELINE_FILTER_PRESETS.moderate.filters.map(f => f.type)

    const present = new Set(filters.map(f => f.type))

    return expected.filter(t => !present.has(t)).map(t => FILTER_META[t]?.label ?? t)

}

