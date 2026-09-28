from pystac_client import Client
import rasterio

# Search planetary computer STAC for ESA WorldCover (2021)
try:
    client = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    search = client.search(
        collections=["esa-worldcover"],
        intersects={"type": "Point", "coordinates": [78.9629, 20.5937]}, # Center of India
        datetime="2021-01-01/2021-12-31"
    )
    items = list(search.items())
    if items:
        item = items[0]
        # Get map URL (COG)
        cog_href = item.assets["map"].href
        print(f"Found COG URL: {cog_href}")
        
        # Sample the COG
        with rasterio.open(cog_href) as src:
            # Generate the pyproj/transformer from lon/lat to the COG CRS
            from pyproj import Transformer
            transformer = Transformer.from_crs("epsg:4326", src.crs, always_xy=True)
            x, y = transformer.transform(78.9629, 20.5937)
            
            # Sample point
            val = list(src.sample([(x, y)]))
            print(f"Sampled Land Cover value: {val[0][0]}")
    else:
        print("No STAC items found.")
except Exception as e:
    print(f"Error: {e}")
