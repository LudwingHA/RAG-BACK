import geopandas as gpd

class GeoProcessor:

    @staticmethod
    def process_geojson(file_path: str) -> str:
        gdf = gpd.read_file(file_path)

        text_data = []

        for _, row in gdf.iterrows():
            attributes = ", ".join([f"{col}: {row[col]}" for col in gdf.columns if col != "geometry"])
            text_data.append(attributes)

        return "\n".join(text_data)
