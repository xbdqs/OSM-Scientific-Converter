#!/usr/bin/env python3
"""Reproducible Sao Paulo real-road publication figure from targeted highway GeoPackage.

Only stdlib + GDAL/OGR (osgeo) required for extraction and vector SVG; PNG/PDF use
PySide6.QtSvg if available, or CairoSVG as fallback. Does not run a new PBF scan.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

CATEGORIES = (
    "residential_and_service",
    "pedestrian",
    "primary_secondary_tertiary",
    "motorways_and_trunks",
)
STYLES = {
    "residential_and_service": {"color": "#9fb1c3", "width": 1.13, "name": "Residential / service"},
    "pedestrian": {"color": "#008f86", "width": 1.7, "name": "Pedestrian"},
    "primary_secondary_tertiary": {"color": "#d47a29", "width": 2.3, "name": "Primary / secondary / tertiary"},
    "motorways_and_trunks": {"color": "#863c68", "width": 3.1, "name": "Motorway / trunk"},
}
# Study-area coordinates are explicit assumptions and may be modified by the user.
MAIN_LONLAT = (-46.69, -23.59, -46.59, -23.51)
DETAIL_LONLAT = (-46.662, -23.569, -46.634, -23.545)
SVG_W, SVG_H = 1700, 1040
MAIN_FRAME = (53, 162, 990, 705)
DETAIL_FRAME = (1102, 162, 545, 705)


def validate_bbox(b):
    if len(b) != 4 or not all(math.isfinite(float(v)) for v in b):
        raise ValueError("Bounds require four finite numeric values")
    a, c, d, e = [float(v) for v in b]
    if not (a < d and c < e and -180 <= a < d <= 180 and -90 <= c < e <= 90):
        raise ValueError("Invalid lon/lat bounding rectangle")
    return a, c, d, e


def inside(inner, outer):
    return outer[0] <= inner[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def quant(x):
    return f"{x:.1f}"


def plot_transform(bounds_m, frame):
    x0, y0, x1, y1 = bounds_m
    fx, fy, fw, fh = frame
    dx, dy = x1 - x0, y1 - y0
    if min(dx, dy) <= 0:
        raise ValueError("Projected map bounds must have positive area")
    scale = min((fw - 30) / dx, (fh - 30) / dy)
    offset_x = fx + (fw - dx * scale) / 2
    offset_y = fy + (fh - dy * scale) / 2
    def position(x, y):
        return offset_x + (x - x0) * scale, offset_y + (y1 - y) * scale
    return position, scale


def svg_line_path(parts, bounds, frame):
    position, _ = plot_transform(bounds, frame)
    chunks = []
    for vertices in parts:
        if len(vertices) < 2:
            continue
        xy = [position(x, y) for x, y in vertices]
        if not all(math.isfinite(x) and math.isfinite(y) for x, y in xy):
            continue
        first = xy[0]
        chunks.append('M' + quant(first[0]) + ',' + quant(first[1]) + ' ' +
                      ' '.join('L' + quant(x) + ',' + quant(y) for x, y in xy[1:]))
    return ' '.join(chunks)


def nice_scale_m(width_m):
    if width_m <= 0:
        raise ValueError("Invalid scale width")
    # Target scale bar at most 1/4 of view width.
    target = width_m / 5
    magnitude = 10 ** math.floor(math.log10(target))
    return max(v * magnitude for v in (1, 2, 5, 10) if v * magnitude <= target)


def svg_map_panel(parts_by_cat, projected_bounds, frame, clip_id, name, detail_rect=None):
    fx, fy, fw, fh = frame
    elements = [f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" fill="#fbfcfe" stroke="#bfc9d3" stroke-width="1.8"/>',
                f'<g clip-path="url(#{clip_id})">']
    # Light GIS grid in UTM projected coordinates.
    xmin, ymin, xmax, ymax = projected_bounds
    pos, scale = plot_transform(projected_bounds, frame)
    step = 2000 if name == 'main' else 500
    xx = math.ceil(xmin / step) * step
    while xx < xmax:
        p1 = pos(xx, ymin); p2 = pos(xx, ymax)
        elements.append(f'<path d="M{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f}" stroke="#e7edf1" stroke-width="1"/>')
        xx += step
    yy = math.ceil(ymin / step) * step
    while yy < ymax:
        p1 = pos(xmin, yy); p2 = pos(xmax, yy)
        elements.append(f'<path d="M{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f}" stroke="#e7edf1" stroke-width="1"/>')
        yy += step
    for category in CATEGORIES:
        path = svg_line_path(parts_by_cat.get(category, []), projected_bounds, frame)
        if path:
            st = STYLES[category]
            elements.append(f'<path d="{path}" stroke="{st["color"]}" stroke-width="{st["width"]}" fill="none" stroke-linejoin="round" stroke-linecap="round"/>')
    if detail_rect:
        (rx0, ry0, rx1, ry1) = detail_rect
        tl = pos(rx0, ry1); br = pos(rx1, ry0)
        elements.append(f'<rect x="{tl[0]:.1f}" y="{tl[1]:.1f}" width="{br[0]-tl[0]:.1f}" height="{br[1]-tl[1]:.1f}" stroke="#db3944" stroke-width="3.4" fill="#ff6b6b" fill-opacity="0.065" stroke-dasharray="11 6"/>')
    elements.append('</g>')
    # North arrow and distance-scale bar (units are UTM meters).
    nx = fx + fw - 38; ny = fy + 34
    elements += [f'<path d="M{nx},{ny+25} L{nx},{ny-12}" stroke="#24374a" stroke-width="2.3"/>',
                 f'<path d="M{nx},{ny-17} l-8,15 h16 z" fill="#24374a"/>',
                 f'<text x="{nx}" y="{ny-24}" text-anchor="middle" class="map-tiny" font-weight="700">N</text>']
    scale_m = nice_scale_m(xmax-xmin)
    length = scale_m * scale
    bx, by = fx + 35, fy + fh - 38
    elements += [f'<path d="M{bx},{by} h{length/2:.2f}" stroke="#24374a" stroke-width="8"/>',
                 f'<path d="M{bx+length/2:.2f},{by} h{length/2:.2f}" stroke="#ffffff" stroke-width="8"/>',
                 f'<path d="M{bx},{by} h{length:.2f}" stroke="#24374a" stroke-width="1.1" fill="none"/>',
                 f'<text x="{bx}" y="{by-11}" class="map-small">0</text>',
                 f'<text x="{bx+length:.2f}" y="{by-11}" text-anchor="end" class="map-small">{scale_m/1000:g} km</text>']
    return '\n'.join(elements)


def create_svg(parts_by_cat, bounds_m, detail_bounds_m, counts, n_total):
    if n_total <= 0:
        raise ValueError("No feature geometry found in selected Sao Paulo area")
    main_clip = f'<clipPath id="map-main"><rect x="{MAIN_FRAME[0]+1}" y="{MAIN_FRAME[1]+1}" width="{MAIN_FRAME[2]-2}" height="{MAIN_FRAME[3]-2}"/></clipPath>'
    detail_clip = f'<clipPath id="map-detail"><rect x="{DETAIL_FRAME[0]+1}" y="{DETAIL_FRAME[1]+1}" width="{DETAIL_FRAME[2]-2}" height="{DETAIL_FRAME[3]-2}"/></clipPath>'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">',
             '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#233345}.fig-title{font-size:32px;font-weight:700}.fig-subtitle{font-size:19px;fill:#5a6b79}.panel-title{font-size:23px;font-weight:700}.map-small{font-size:17px}.map-tiny{font-size:19px}.legend{font-size:20px}</style>',
             f'<defs>{main_clip}{detail_clip}</defs>',
             '<rect width="1700" height="1040" fill="white"/>',
             '<text class="fig-title" x="52" y="54">Road-network extraction in central São Paulo, Brazil</text>',
             '<text class="fig-subtitle" x="52" y="91">Selected OSM highway classes · fixed Sudeste 2026-09-01 snapshot · GDAL lines layer</text>',
             '<text class="panel-title" x="55" y="143">A  Urban study area</text>',
             '<text class="panel-title" x="1104" y="143">B  Enlarged detail</text>',
             svg_map_panel(parts_by_cat, bounds_m, MAIN_FRAME, 'map-main', 'main', detail_bounds_m),
             svg_map_panel(parts_by_cat, detail_bounds_m, DETAIL_FRAME, 'map-detail', 'detail')]
    parts.append('<text class="map-small" x="55" y="899">Categories displayed (drawn over a common spatial subset)</text>')
    xs = [62, 496, 885, 1258]
    for cat, x in zip(("motorways_and_trunks","primary_secondary_tertiary","residential_and_service","pedestrian"), xs):
        st = STYLES[cat]
        parts.append(f'<path d="M{x},936 h40" fill="none" stroke="{st["color"]}" stroke-width="{max(st["width"]*1.7,3):.2f}" stroke-linecap="round"/>')
        parts.append(f'<text x="{x+48}" y="943" class="legend">{escape(st["name"])} ({counts.get(cat, 0):,})</text>')
    parts.extend([
        '<path d="M52,970 H1648" stroke="#d2dce5" stroke-width="1.5"/>',
        '<text x="52" y="998" class="map-small">Coordinates and scale: WGS 84 / UTM 23S (EPSG:32723). OSM road classes shown are a reviewed subset.</text>',
        '<text x="52" y="1024" class="map-small">© OpenStreetMap contributors (ODbL). No basemap. Bounded spatial visualization; not a road-completeness audit.</text>',
        '</svg>'])
    return '\n'.join(parts)


def atomic_write_text(path, content):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content, encoding='utf-8')
    os.replace(temporary, path)


def flatten_linear(geometry, ogr):
    if not geometry or geometry.IsEmpty():
        return
    typ = ogr.GT_Flatten(geometry.GetGeometryType())
    if typ in (ogr.wkbLineString, ogr.wkbLinearRing):
        yield geometry
    elif typ in (ogr.wkbMultiLineString, ogr.wkbGeometryCollection):
        for j in range(geometry.GetGeometryCount()):
            yield from flatten_linear(geometry.GetGeometryRef(j), ogr)


def rectangle_wkt(b):
    x0,y0,x1,y1=b
    return (f'POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},'
            f'{x0} {y1},{x0} {y0}))')


def source_area_to_projected_bounds(b, tx):
    # Transform corners plus mid-edges so axis-rotation effects don't crop an edge.
    x0,y0,x1,y1=b
    vertices=[(x0,y0),(x0,y1),(x1,y0),(x1,y1),((x0+x1)/2,y0),((x0+x1)/2,y1),
              (x0,(y0+y1)/2),(x1,(y0+y1)/2)]
    points=[tx.TransformPoint(lon,lat) for lon,lat in vertices]
    return min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)


def projected_polyline(geometry):
    return [(geometry.GetX(j),geometry.GetY(j)) for j in range(geometry.GetPointCount())]


def build_from_real_gpkg(input_path, out_dir, main_bbox, detail_bbox, max_features):
    from osgeo import gdal, ogr, osr
    ogr.UseExceptions()
    gdal.UseExceptions()
    dataset=ogr.Open(str(input_path), 0)
    if dataset is None:
        raise RuntimeError(f'Cannot open input GeoPackage: {input_path}')
    layer=dataset.GetLayerByName('highway_lines')
    if layer is None:
        raise ValueError('Expected input layer highway_lines missing; supply a quick-extract GPKG')
    src_srs=layer.GetSpatialRef()
    if src_srs is None:
        raise ValueError('Input source CRS missing')
    src_srs=src_srs.Clone()
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    expected=osr.SpatialReference();expected.ImportFromEPSG(4326)
    expected.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    if not src_srs.IsSame(expected):
        raise ValueError('Expected EPSG:4326 input; reproject independently before making the map')
    dst_srs=osr.SpatialReference();dst_srs.ImportFromEPSG(32723)
    dst_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx=osr.CoordinateTransformation(src_srs,dst_srs)
    projected_main=source_area_to_projected_bounds(main_bbox,tx)
    projected_detail=source_area_to_projected_bounds(detail_bbox,tx)
    rect=ogr.CreateGeometryFromWkt(rectangle_wkt(main_bbox))
    rect.AssignSpatialReference(src_srs)
    layer.SetSpatialFilterRect(*main_bbox)
    cols=[layer.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(layer.GetLayerDefn().GetFieldCount())]
    required={'category','highway','source_layer','canonical_osm_id','profile_sha256','tags_json'}
    if not required.issubset(set(cols)):
        raise ValueError(f'Expected audit fields absent: {sorted(required-set(cols))}')
    driver=ogr.GetDriverByName('GPKG')
    if not driver:
        raise RuntimeError('GDAL GeoPackage driver unavailable')
    temporary=out_dir/'sao_paulo_selected_roads.partial.gpkg'
    final=out_dir/'sao_paulo_selected_roads.gpkg'
    if temporary.exists(): temporary.unlink()
    output=driver.CreateDataSource(str(temporary))
    if output is None: raise RuntimeError('Cannot create output GPKG')
    out_layer=output.CreateLayer('selected_highway_lines', dst_srs, geom_type=ogr.wkbMultiLineString,
                                 options=['SPATIAL_INDEX=YES'])
    for i in range(layer.GetLayerDefn().GetFieldCount()):
        field_def=layer.GetLayerDefn().GetFieldDefn(i)
        out_layer.CreateField(field_def)
    defn=out_layer.GetLayerDefn()
    counts=Counter()
    profile_hashes=set()
    objects=0
    parts={c:[] for c in CATEGORIES}
    skipped_empty=0
    skipped_non_line=0
    try:
        for feature in layer:
            category=feature.GetField('category')
            if category not in STYLES:
                raise ValueError(f'Unrecognized category {category!r} at fid {feature.GetFID()}')
            if feature.GetField('source_layer')!='lines':
                raise ValueError(f'Input includes other source layer: {feature.GetField("source_layer")}')
            geom=feature.GetGeometryRef()
            if not geom or geom.IsEmpty():
                skipped_empty+=1
                continue
            cut=geom.Intersection(rect)
            if not cut or cut.IsEmpty():
                continue
            multi=ogr.Geometry(ogr.wkbMultiLineString)
            for g in flatten_linear(cut,ogr):
                cp=g.Clone()
                cp.FlattenTo2D()
                if cp.GetPointCount()>=2:
                    multi.AddGeometry(cp)
            if not multi.GetGeometryCount():
                skipped_non_line+=1
                continue
            multi.AssignSpatialReference(src_srs)
            if multi.Transform(tx)!=0:
                raise RuntimeError('Reprojection to EPSG:32723 failed')
            obj=ogr.Feature(defn)
            for field_name in cols:
                if feature.IsFieldSet(field_name): obj.SetField(field_name,feature.GetField(field_name))
            obj.SetGeometry(multi)
            if out_layer.CreateFeature(obj)!=0:
                raise RuntimeError('Cannot write GeoPackage feature')
            objects+=1
            counts[category]+=1
            profile_hashes.add(str(feature.GetField('profile_sha256')))
            for j in range(multi.GetGeometryCount()):
                coords=projected_polyline(multi.GetGeometryRef(j))
                if len(coords)>1:
                    parts[category].append(coords)
            if objects%5000==0: print(f'   Written {objects:,} selected objects ...',flush=True)
            if objects > max_features:
                raise RuntimeError(f'AOI > --max-features ({max_features:,}); select a smaller bounding box')
        out_layer=None;output=None
    except Exception:
        out_layer=None;output=None
        try: temporary.unlink()
        except OSError: pass
        raise
    finally:
        layer.SetSpatialFilter(None)
        layer=None;dataset=None
    if objects==0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError('No accepted features intersect AOI. Check the input GeoPackage and bounding box.')
    if len(profile_hashes)!=1 or not next(iter(profile_hashes)):
        raise RuntimeError('Inconsistent or missing input profile SHA-256 in AOI')
    verify=ogr.Open(str(temporary),0)
    if not verify: raise RuntimeError('Clipped GeoPackage cannot be reopened')
    verified_layer=verify.GetLayerByName('selected_highway_lines')
    if verified_layer is None or verified_layer.GetFeatureCount()!=objects:
        raise RuntimeError('Clipped GeoPackage feature count validation failed')
    verified_layer=None;verify=None
    if final.exists():
        raise FileExistsError(f'Refusing to replace existing result: {final}')
    os.replace(temporary,final)
    return parts,projected_main,projected_detail,counts,objects,skipped_empty,skipped_non_line,final,next(iter(profile_hashes))


def export_optional_rasters(svg_path, png_path, pdf_path):
    warnings=[]
    try:
        from PySide6.QtGui import QGuiApplication,QImage,QPainter,QPdfWriter,QPageSize
        from PySide6.QtCore import QSizeF,QMarginsF
        from PySide6.QtSvg import QSvgRenderer
        app=QGuiApplication.instance() or QGuiApplication([])
        renderer=QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            raise RuntimeError('Qt failed to parse SVG')
        image=QImage(SVG_W*2,SVG_H*2,QImage.Format_ARGB32)
        image.fill(0xffffffff)
        painter=QPainter(image);renderer.render(painter);painter.end()
        if not image.save(str(png_path),'PNG'):
            raise RuntimeError('Cannot save PNG')
        # Qt's PDF engine uses the same vector SVG renderer; output is page-sized.
        pdf=QPdfWriter(str(pdf_path))
        pdf.setResolution(150)
        pdf.setPageSize(QPageSize(QSizeF(SVG_W/150*25.4,SVG_H/150*25.4),QPageSize.Millimeter))
        pdf.setPageMargins(QMarginsF(0,0,0,0))
        p=QPainter(pdf);renderer.render(p);p.end()
        return 'QtSvg',warnings
    except Exception as error:
        warnings.append('QtSvg image/PDF export failed: '+str(error))
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path),write_to=str(png_path),output_width=SVG_W*2,output_height=SVG_H*2)
        cairosvg.svg2pdf(url=str(svg_path),write_to=str(pdf_path))
        return 'CairoSVG',warnings
    except Exception as error:
        warnings.append('Optional CairoSVG export unavailable: '+str(error))
        return 'SVG only',warnings


def main(argv=None):
    ap=argparse.ArgumentParser(description='Publication map from already-extracted Brazil Sudeste roads GeoPackage')
    ap.add_argument('--gpkg',required=True,type=Path,help='Previous targeted/default_roads.gpkg')
    ap.add_argument('--out',required=True,type=Path,help='New output folder (must not contain existing figure GPKG)')
    ap.add_argument('--main-bbox',nargs=4,type=float,default=MAIN_LONLAT,metavar=('W','S','E','N'))
    ap.add_argument('--detail-bbox',nargs=4,type=float,default=DETAIL_LONLAT,metavar=('W','S','E','N'))
    ap.add_argument('--max-features',type=int,default=150000)
    ap.add_argument('--benchmark-summary',type=Path,default=None,help='Optional prior A/B summary.json for provenance')
    args=ap.parse_args(argv)
    main_bbox=validate_bbox(args.main_bbox);detail_bbox=validate_bbox(args.detail_bbox)
    if not inside(detail_bbox,main_bbox): ap.error('--detail-bbox must lie within --main-bbox')
    if args.max_features<1: ap.error('--max-features must be positive')
    source=args.gpkg.expanduser().resolve();out=args.out.expanduser().resolve()
    if not source.is_file(): ap.error('GeoPackage file does not exist: '+str(source))
    out.mkdir(parents=True,exist_ok=True)
    for name in ('figure_sao_paulo_selected_roads.svg','figure_sao_paulo_selected_roads.png',
                 'figure_sao_paulo_selected_roads.pdf','figure_metadata.json','category_counts.csv',
                 'sao_paulo_selected_roads.gpkg'):
        if (out/name).exists(): ap.error(f'Refusing to replace existing output file: {out/name}. Use a new --out.')
    print('Input:',source,'\nAOI:',main_bbox,'\nDetail:',detail_bbox,flush=True)
    parts,bounds,detail,counts,total,skipped_empty,skipped_non_line,aoi,profile_hash=build_from_real_gpkg(
        source,out,main_bbox,detail_bbox,args.max_features)
    print('AOI features:',total,'category counts:',dict(counts),flush=True)
    svg=out/'figure_sao_paulo_selected_roads.svg'
    atomic_write_text(svg,create_svg(parts,bounds,detail,counts,total))
    renderer,warnings=export_optional_rasters(svg,out/'figure_sao_paulo_selected_roads.png',out/'figure_sao_paulo_selected_roads.pdf')
    prior={}
    if args.benchmark_summary:
        if not args.benchmark_summary.is_file(): raise FileNotFoundError(args.benchmark_summary)
        summary=json.loads(args.benchmark_summary.read_text(encoding='utf-8'))
        prior={k:summary.get(k) for k in ('experiment','input_file','input_sha256','rules_sha256')}
        if prior.get('rules_sha256') and prior['rules_sha256']!=profile_hash:
            raise ValueError('Benchmark rule SHA-256 differs from selected AOI profile SHA-256')
    stats={
        'map_status':'success',
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'source_gpkg':str(source),
        'source_size_bytes':source.stat().st_size,
        'source_gpkg_sha256':None,
        'source_gpkg_hash_note':'Not hashed in this workflow; PBF hash from benchmark summary if supplied.',
        'input_layer':'highway_lines',
        'input_profile_sha256':profile_hash,
        'output_layer':'selected_highway_lines',
        'main_bbox_lonlat':main_bbox,'detail_bbox_lonlat':detail_bbox,
        'projected_crs':'EPSG:32723',
        'aoi_feature_count':total,
        'aoi_class_counts':dict(counts),
        'missing_geometry_rows_skipped':skipped_empty,
        'non_linear_intersection_rows_skipped':skipped_non_line,
        'output_file':aoi.name,'figure_svg':svg.name,
        'figure_png':('figure_sao_paulo_selected_roads.png' if (out/'figure_sao_paulo_selected_roads.png').exists() else None),
        'figure_pdf':('figure_sao_paulo_selected_roads.pdf' if (out/'figure_sao_paulo_selected_roads.pdf').exists() else None),
        'renderer':renderer,'render_warnings':warnings,
        'benchmark_evidence':prior,
        'scope':'Only 13 reviewed OSM highway values, source layer lines; not a complete road inventory; bounded AOI, not representative of Sudeste.'
    }
    atomic_write_text(out/'figure_metadata.json',json.dumps(stats,indent=2,ensure_ascii=False))
    with (out/'category_counts.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['category','aoi_features']);w.writerows((cat,counts[cat]) for cat in CATEGORIES)
    caption=(
        'Figure X. Spatial distribution of selected OpenStreetMap highway classes in central São Paulo, Brazil. '
        '(A) Bounded urban study area; (B) enlarged subsection indicated by the rectangle in (A). '
        f'The area-of-interest dataset contains {total:,} extracted line features across four reviewed categories, '
        'from the fixed 1 September 2026 Sudeste OSM PBF snapshot. Classes are limited to 13 reviewed highway '
        'values in the GDAL lines source layer; the map does not depict the complete street network or establish '
        'spatial completeness. The output was reprojected to WGS 84 / UTM zone 23S (EPSG:32723) for rendering. '
        '© OpenStreetMap contributors, ODbL. [Verify counts, study-area wording and figure numbering after execution.]'
    )
    atomic_write_text(out/'figure_caption_draft.txt',caption+'\n')
    print('SUCCESS\n',json.dumps({k:stats[k] for k in ('aoi_feature_count','aoi_class_counts','figure_png','figure_pdf','renderer')},indent=2))
    print('Output folder:',out)
    if warnings: print('Rendering notes:',warnings)
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(f'[ERROR] {exc}',file=sys.stderr)
        raise SystemExit(2)
