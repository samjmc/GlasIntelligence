import { describe, it, expect } from 'vitest'
import {
  getGraphPollIntervalMs,
  graphPollMsVisible,
  graphPollMsHidden,
  graphPollDuringBuildMs,
} from './zepFootprint'

describe('zepFootprint', () => {
  it('hidden tab uses hidden interval', () => {
    expect(getGraphPollIntervalMs({ documentHidden: true })).toBe(graphPollMsHidden)
  })

  it('visible + building uses during-build interval', () => {
    expect(
      getGraphPollIntervalMs({ graphBuilding: true, documentHidden: false }),
    ).toBe(graphPollDuringBuildMs)
  })

  it('visible + not building uses visible interval', () => {
    expect(getGraphPollIntervalMs({ graphBuilding: false, documentHidden: false })).toBe(
      graphPollMsVisible,
    )
  })

  it('hidden wins over building', () => {
    expect(getGraphPollIntervalMs({ graphBuilding: true, documentHidden: true })).toBe(
      graphPollMsHidden,
    )
  })
})
