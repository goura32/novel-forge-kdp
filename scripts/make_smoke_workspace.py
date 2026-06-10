from pathlib import Path
from novel_forge_kdp.models import SeriesPlan, World, Character, PlannedVolume, ProjectState, VolumeProgress, SceneProgress
from novel_forge_kdp.workflow import NovelForge

root = Path('smoke_workspace')
slug = 'smoke-one-scene'
series_dir = root / slug
scene_dir = series_dir / 'volume_001' / 'chapters' / 'chapter_001'
scene_dir.mkdir(parents=True, exist_ok=True)
series = SeriesPlan(
    title='煙突町の小さな星',
    slug=slug,
    logline='星を修理する少女の短い冒険。',
    genre='短編ファンタジー',
    target_audience='KDP読者',
    themes=['希望'],
    selling_points=['短く読める', '情緒的'],
    world=World(summary='煙突だらけの町。', rules=['星は修理できる']),
    main_characters=[Character(name='ミナ', role='星修理師', arc='自信を得る')],
    planned_volumes=[PlannedVolume(number=1, title='煙突町の小さな星', premise='壊れた星を直す。')],
)
state = ProjectState(
    series=series,
    current_volume=1,
    volumes=[VolumeProgress(number=1, title='煙突町の小さな星', status='drafted', scenes=[SceneProgress(chapter=1, scene=1, title='落ちた星', status='revised', path='volume_001/chapters/chapter_001/scene_001.md')])],
)
NovelForge._write_json(series_dir / 'series_plan.json', series.model_dump())
NovelForge._write_json(series_dir / 'state.json', state.model_dump())
(scene_dir / 'scene_001.md').write_text('# 落ちた星\n\nミナは煙突の影で、ひび割れた小さな星を拾った。星はまだ温かく、彼女の掌でかすかに瞬いていた。\n', encoding='utf-8')
print(series_dir)
