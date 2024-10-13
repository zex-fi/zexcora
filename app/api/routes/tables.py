from typing import Any
import os
import sqlite3


class Direction:
    ASCENDING = "ASC"
    DESCENDING = "DESC"


class Entity:
    table_name: str = None
    columns: list = None

    def __init__(self, db_path: str):
        self.db_path = db_path

        if not os.path.exists(db_path):
            with open("init_db.sql") as fp:
                statements = fp.read().split(";")
            for statement in statements:
                query = statement.strip()
                if query:
                    self.exe_query(query)

    def exe_query(self, query, params=()):
        con_obj = sqlite3.connect(self.db_path)
        courser = con_obj.execute(query, params)
        res = courser.fetchall()
        con_obj.commit()
        con_obj.close()
        return res

    def find_one(
        self,
        filter: dict[str, Any] = None,
        projection: list[str] = None,
        order_by: str = None,
        direction: str = Direction.ASCENDING,
    ):
        result = self.find(filter, projection, order_by, direction, limit=1)
        if result:
            return result[0]
        return None

    def find(
        self,
        filter: dict[str, Any] = None,
        projection: list[str] = None,
        order_by: str = None,
        direction: str = Direction.ASCENDING,
        limit: int = None,
    ):
        if projection is None:
            projection = self.columns

        if filter is None:
            filter = {}

        to_select = ", ".join(f'"{c}"' for c in projection)

        query = f"SELECT {to_select} FROM {self.table_name}"
        params = tuple(filter.values())
        condition = " AND ".join(f'"{a}" = ?' for a in filter.keys())
        if condition:
            query += f" WHERE {condition}"
        if order_by:
            query += f' ORDER BY "{order_by}" {direction}'
        if limit:
            query += f" LIMIT {limit}"

        result = self.exe_query(query, params)
        return [dict(zip(projection, row, strict=False)) for row in result]

    def insert_one(self, document: dict):
        assert self.table_name
        params = tuple(document.values())
        values_template = ", ".join("?" for _ in range(len(params)))
        attributes = ", ".join(f'"{a}"' for a in document.keys())
        self.exe_query(
            f"INSERT INTO {self.table_name}({attributes}) VALUES({values_template})",
            params,
        )
        inserted_id = self.exe_query(
            f"SELECT seq FROM sqlite_sequence WHERE name='{self.table_name}'"
        )[0][0]
        return inserted_id

    def update_one(self, filter: dict, update: dict, upsert: bool = False):
        assert self.table_name
        if upsert and not self.find_one(filter):
            return self.insert_one(filter | update)
        params = tuple(update.values()) + tuple(filter.values())
        values = ", ".join(f'"{a}" = ?' for a in update.keys())
        condition = " AND ".join(f'"{a}" = ?' for a in filter.keys())
        self.exe_query(
            f"UPDATE {self.table_name} SET {values} WHERE {condition};", params
        )

    def delete_one(self, filter: dict):
        assert self.table_name
        params = tuple(filter.values())
        condition = " AND ".join(f'"{a}" = ?' for a in filter.keys())
        self.exe_query(f"DELETE FROM {self.table_name} WHERE {condition};", params)


class Chart(Entity):
    table_name = "Chart"
    columns = [
        "id",
        "owner_source",
        "owner_id",
        "name",
        "content",
        "timestamp",
        "symbol",
        "resolution",
    ]


class Study(Entity):
    table_name = "Study"
    columns = ["id", "owner_source", "owner_id", "name", "content"]


class Drawing(Entity):
    table_name = "Drawing"
    columns = ["id", "owner_source", "owner_id", "tool", "name", "content"]
