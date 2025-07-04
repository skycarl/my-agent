class Sneaker:
    def __init__(self, id, brand_name, name, description, size, color, free_delivery):
        self.id = id
        self.brand_name = brand_name
        self.name = name
        self.description = description
        self.size = size
        self.color = color
        self.free_delivery = free_delivery

    class Config:
        orm_mode = True
