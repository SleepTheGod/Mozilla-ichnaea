import base64

import numpy

from ichnaea.data.base import DataTask
from ichnaea.geocalc import (
    centroid,
    circle_radius,
)
from ichnaea.models import (
    decode_cellarea,
    encode_cellarea,
    Cell,
    CellArea,
    OCIDCell,
    OCIDCellArea,
)
from ichnaea.models.cell import CellAreaKey
from ichnaea import util


class CellAreaUpdater(DataTask):

    cell_model = Cell
    area_model = CellArea

    def __init__(self, task, session):
        DataTask.__init__(self, task, session)
        self.data_queue = self.task.app.data_queues['update_cellarea']
        self.utcnow = util.utcnow()

    def scan(self, update_task, batch=100):
        redis_areas = self.data_queue.dequeue(batch=batch)
        # BBB deal with hashkeys and mixed ids/hashkeys
        areaids = set()
        for areaid in redis_areas:
            if isinstance(areaid, CellAreaKey):  # pragma: no cover
                areaid = encode_cellarea(
                    areaid.radio,
                    areaid.mcc,
                    areaid.mnc,
                    areaid.lac,
                    codec='base64')
            areaids.add(areaid)

        areaids = list(areaids)
        batch_size = 10
        for i in range(0, len(areaids), batch_size):
            area_batch = areaids[i:i + batch_size]
            update_task.delay(area_batch)
        return len(areaids)

    def update(self, areaids):
        # BBB deal with hashkeys and mixed ids/hashkeys
        ids = set()
        for areaid in areaids:
            if isinstance(areaid, CellAreaKey):  # pragma: no cover
                areaid = encode_cellarea(
                    areaid.radio,
                    areaid.mcc,
                    areaid.mnc,
                    areaid.lac,
                    codec='base64')
            ids.add(base64.b64decode(areaid))
        for id_ in ids:
            self.update_area(id_)

    def update_area(self, areaid):
        radio, mcc, mnc, lac = decode_cellarea(areaid)
        # Select all cells in this area and derive a bounding box for them
        cells = (self.session.query(self.cell_model)
                             .filter(self.cell_model.radio == radio)
                             .filter(self.cell_model.mcc == mcc)
                             .filter(self.cell_model.mnc == mnc)
                             .filter(self.cell_model.lac == lac)
                             .filter(self.cell_model.lat.isnot(None))
                             .filter(self.cell_model.lon.isnot(None))).all()

        area_query = (self.session.query(self.area_model)
                                  .filter(self.area_model.radio == radio)
                                  .filter(self.area_model.mcc == mcc)
                                  .filter(self.area_model.mnc == mnc)
                                  .filter(self.area_model.lac == lac))

        if len(cells) == 0:
            # If there are no more underlying cells, delete the area entry
            area_query.delete()
        else:
            # Otherwise update the area entry based on all the cells
            area = area_query.first()

            cell_extremes = numpy.array([
                (numpy.nan if cell.max_lat is None else cell.max_lat,
                 numpy.nan if cell.max_lon is None else cell.max_lon)
                for cell in cells] + [
                (numpy.nan if cell.min_lat is None else cell.min_lat,
                 numpy.nan if cell.min_lon is None else cell.min_lon)
                for cell in cells
            ], dtype=numpy.double)

            max_lat, max_lon = numpy.nanmax(cell_extremes, axis=0)
            min_lat, min_lon = numpy.nanmin(cell_extremes, axis=0)

            ctr_lat, ctr_lon = centroid(
                numpy.array([(c.lat, c.lon) for c in cells],
                            dtype=numpy.double))
            radius = circle_radius(
                ctr_lat, ctr_lon,
                max_lat, max_lon, min_lat, min_lon)

            # Now create or update the area
            cell_ranges = numpy.array([
                (numpy.nan if cell.range is None else cell.range)
                for cell in cells
            ], dtype=numpy.int32)
            avg_cell_range = int(round(numpy.nanmean(cell_ranges)))
            num_cells = len(cells)

            if area is None:
                stmt = self.area_model.__table__.insert(
                    mysql_on_duplicate='num_cells = num_cells'  # no-op
                ).values(
                    created=self.utcnow,
                    modified=self.utcnow,
                    lat=ctr_lat,
                    lon=ctr_lon,
                    range=radius,
                    avg_cell_range=avg_cell_range,
                    num_cells=num_cells,
                    radio=radio,
                    mcc=mcc,
                    mnc=mnc,
                    lac=lac,
                    areaid=areaid,
                )
                self.session.execute(stmt)
            else:
                area.modified = self.utcnow
                area.lat = ctr_lat
                area.lon = ctr_lon
                area.range = radius
                area.avg_cell_range = avg_cell_range
                area.num_cells = num_cells


class OCIDCellAreaUpdater(CellAreaUpdater):

    cell_model = OCIDCell
    area_model = OCIDCellArea
