import { useEffect, useRef } from "react";
import L from "leaflet";
import type { Clinic, Selection, Warehouse } from "../types";

type MapViewProps = {
  clinics: Clinic[];
  warehouses: Warehouse[];
  selected: Selection | null;
  onSelect: (selection: Selection) => void;
};

const RISK_CLASS: Record<Clinic["risk_level"], string> = {
  normal: "marker-normal",
  medium: "marker-medium",
  high: "marker-high",
  critical: "marker-critical",
};

export function MapView({
  clinics,
  warehouses,
  selected,
  onSelect,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = L.map(containerRef.current, {
      center: [-4.4419, 15.2663],
      zoom: 11,
      zoomControl: false,
    });

    L.control.zoom({ position: "bottomleft" }).addTo(map);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) {
      return;
    }

    layer.clearLayers();

    clinics.forEach((clinic) => {
      const isSelected =
        selected?.type === "clinic" && selected.id === clinic.id;
      const marker = L.marker([clinic.latitude, clinic.longitude], {
        icon: L.divIcon({
          className: "",
          html: `<span class="clinic-marker ${RISK_CLASS[clinic.risk_level]} ${
            isSelected ? "marker-selected" : ""
          }"></span>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        }),
      }).bindTooltip(clinic.name);
      marker.on("click", () => onSelect({ type: "clinic", id: clinic.id }));
      marker.addTo(layer);
    });

    warehouses.forEach((warehouse) => {
      const isSelected =
        selected?.type === "warehouse" && selected.id === warehouse.id;
      const marker = L.marker([warehouse.latitude, warehouse.longitude], {
        icon: L.divIcon({
          className: "",
          html: `<span class="warehouse-marker ${
            isSelected ? "marker-selected" : ""
          }"><span>${warehouse.test_kits_stock}</span></span>`,
          iconSize: [34, 34],
          iconAnchor: [17, 17],
        }),
      }).bindTooltip(warehouse.name);
      marker.on("click", () =>
        onSelect({ type: "warehouse", id: warehouse.id }),
      );
      marker.addTo(layer);
    });
  }, [clinics, warehouses, selected, onSelect]);

  return <div ref={containerRef} className="h-full min-h-[420px] w-full" />;
}
